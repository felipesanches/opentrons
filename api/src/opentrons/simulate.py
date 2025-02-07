""" opentrons.simulate: functions and entrypoints for simulating protocols

This module has functions that provide a console entrypoint for simulating
a protocol from the command line.
"""

import argparse

import sys
import logging
import os
import pathlib
import queue
from typing import Any, Dict, List, Mapping, TextIO, Tuple, BinaryIO, Optional


import opentrons
import opentrons.commands
import opentrons.broker
import opentrons.config
from opentrons.protocols import parse, bundle
from opentrons.protocols.types import (
    JsonProtocol, PythonProtocol, BundleContents)
from opentrons.protocol_api import execute
from .util.entrypoint_util import labware_from_paths, datafiles_from_paths


class AccumulatingHandler(logging.Handler):
    def __init__(self, level, command_queue):
        """ Create the handler

        :param level: The logging level to capture
        :param command_queue: The queue.Queue to use for messages
        """
        self._command_queue = command_queue
        super().__init__(level)

    def emit(self, record):
        self._command_queue.put(record)


class CommandScraper:
    """ An object that handles scraping the broker for commands

    This should be instantiated with the logger to integrate
    messages from (e.g. ``logging.getLogger('opentrons')``), the
    level to scrape, and the opentrons broker object to subscribe to.

    The :py:attr:`commands` property contains the list of commands
    and log messages integrated together. Each element of the list is
    a dict following the pattern in the docs of :py:meth:`simulate`.
    """
    def __init__(self,
                 logger: logging.Logger,
                 level: str,
                 broker: opentrons.broker.Broker) -> None:
        """ Build the scraper.

        :param logger: The :py:class:`logging.logger` to scrape
        :param level: The log level to scrape
        :param broker: Which broker to subscribe to
        """
        self._logger = logger
        self._broker = broker
        self._queue = queue.Queue()  # type: ignore
        if level != 'none':
            level = getattr(logging, level.upper(), logging.WARNING)
            self._logger.setLevel(level)
            logger.addHandler(
                AccumulatingHandler(
                    level,
                    self._queue))
        self._depth = 0
        self._commands: List[Mapping[str, Mapping[str, Any]]] = []
        self._unsub = self._broker.subscribe(
            opentrons.commands.command_types.COMMAND,
            self._command_callback)

    @property
    def commands(self) -> List[Mapping[str, Mapping[str, Any]]]:
        """ The list of commands. See :py:meth:`simulate` """
        return self._commands

    def __del__(self):
        if hasattr(self, '_handler'):
            self._logger.removeHandler(self._handler)
        if hasattr(self, '_unsub'):
            self._unsub()

    def _command_callback(self, message):
        """ The callback subscribed to the broker """
        payload = message['payload']
        if message['$'] == 'before':
            self._commands.append({'level': self._depth,
                                   'payload': payload,
                                   'logs': []})
            self._depth += 1
        else:
            while not self._queue.empty():
                self._commands[-1]['logs'].append(self._queue.get())
            self._depth = max(self._depth-1, 0)


def bundle_from_sim(
        protocol: PythonProtocol,
        context: opentrons.protocol_api.ProtocolContext)\
        -> BundleContents:
    """
    From a protocol, and the context that has finished simulating that
    protocol, determine what needs to go in a bundle for the protocol.
    """
    bundled_labware: Dict[str, Dict[str, Any]] = {}
    for lw in context.loaded_labwares.values():
        if isinstance(lw, opentrons.protocol_api.labware.Labware)\
           and lw.uri not in bundled_labware:
            bundled_labware[lw.uri] = lw._definition

    return BundleContents(protocol.text,
                          bundled_data=context.bundled_data,
                          bundled_labware=bundled_labware,
                          bundled_python={})


def simulate(protocol_file: TextIO,
             file_name: str,
             custom_labware_paths=None,
             custom_data_paths=None,
             propagate_logs=False,
             log_level='warning') -> Tuple[List[Mapping[str, Any]],
                                           Optional[BundleContents]]:
    """
    Simulate the protocol itself.

    This is a one-stop function to simulate a protocol, whether python or json,
    no matter the api version, from external (i.e. not bound up in other
    internal server infrastructure) sources.

    To simulate an opentrons protocol from other places, pass in a file like
    object as protocol_file; this function either returns (if the simulation
    has no problems) or raises an exception.

    To call from the command line use either the autogenerated entrypoint
    ``opentrons_simulate`` (``opentrons_simulate.exe``, on windows) or
    ``python -m opentrons.simulate``.

    The return value is the run log, a list of dicts that represent the
    commands executed by the robot; and either the contents of the protocol
    that would be required to bundle, or ``None``.

    Each dict element in the run log has the following keys:

        - ``level``: The depth at which this command is nested - if this an
                     aspirate inside a mix inside a transfer, for instance,
                     it would be 3.
        - ``payload``: The command, its arguments, and how to format its text.
                       For more specific details see
                       :py:mod:`opentrons.commands`. To format a message from
                       a payload do ``payload['text'].format(**payload)``.
        - ``logs``: Any log messages that occurred during execution of this
                    command, as a logging.LogRecord

    :param file-like protocol_file: The protocol file to simulate.
    :param str file_name: The name of the file
    :param custom_labware_paths: A list of directories to search for custom
                                 labware, or None. Ignored if the apiv2 feature
                                 flag is not set. Loads valid labware from
                                 these paths and makes them available to the
                                 protocol context.
    :param custom_data_paths: A list of directories or files to load custom
                              data files from. Ignored if the apiv2 feature
                              flag if not set. Entries may be either files or
                              directories. Specified files and the
                              non-recursive contents of specified directories
                              are presented by the protocol context in
                              :py:attr:`.ProtocolContext.bundled_data`.
    :param propagate_logs: Whether this function should allow logs from the
                           Opentrons stack to propagate up to the root handler.
                           This can be useful if you're integrating this
                           function in a larger application, but most logs that
                           occur during protocol simulation are best associated
                           with the actions in the protocol that cause them.
                           Default: ``False``
    :type propagate_logs: bool
    :param log_level: The level of logs to capture in the runlog. Default:
                      ``'warning'``
    :type log_level: 'debug', 'info', 'warning', or 'error'
    :returns: A tuple of a run log for user output, and possibly the required
              data to write to a bundle to bundle this protocol. The bundle is
              only emitted if the API v2 feature flag is set and this is an
              unbundled python protocol. In other cases it is None.
    """
    stack_logger = logging.getLogger('opentrons')
    stack_logger.propagate = propagate_logs

    contents = protocol_file.read()
    if custom_labware_paths:
        extra_labware = labware_from_paths(custom_labware_paths)
    else:
        extra_labware = {}
    if custom_data_paths:
        extra_data = datafiles_from_paths(custom_data_paths)
    else:
        extra_data = {}

    protocol = parse.parse(contents, file_name,
                           extra_labware=extra_labware,
                           extra_data=extra_data)

    if opentrons.config.feature_flags.use_protocol_api_v2():
        if isinstance(protocol, PythonProtocol)\
           and protocol.api_level == '1'\
           and not opentrons.config.feature_flags.enable_backcompat():
            raise RuntimeError(
                'This protocol targets Protocol API V1, but the robot is '
                'set to Protocol API V2. If this is actually a V2 '
                'protocol, please set the \'apiLevel\' to \'2\' in the '
                'metadata. If you do not want to be on API V2, please '
                'disable the \'Use Protocol API version 2\' toggle in the '
                'robot\'s Advanced Settings and restart the robot.')
        context = opentrons.protocol_api.contexts.ProtocolContext(
            bundled_labware=getattr(protocol, 'bundled_labware', None),
            bundled_data=getattr(protocol, 'bundled_data', None))
        context.home()
        scraper = CommandScraper(stack_logger, log_level, context.broker)
        execute.run_protocol(protocol,
                             simulate=True,
                             context=context)
        if isinstance(protocol, PythonProtocol)\
           and protocol.bundled_labware is None:
            bundle_contents: Optional[BundleContents] = bundle_from_sim(
                protocol, context)
        else:
            bundle_contents = None
    else:

        def _simulate_v1():
            import opentrons.legacy_api.protocols
            opentrons.robot.disconnect()
            scraper = CommandScraper(stack_logger, log_level,
                                     opentrons.robot.broker)
            if isinstance(protocol, JsonProtocol):
                opentrons.legacy_api.protocols.execute_protocol(protocol)
            else:
                exec(protocol.contents, {})
            return scraper

        scraper = _simulate_v1()
        bundle_contents = None

    return scraper.commands, bundle_contents


def format_runlog(runlog: List[Mapping[str, Any]]) -> str:
    """
    Format a run log (return value of :py:meth:`simulate``) into a
    human-readable string

    :param runlog: The output of a call to :py:func:`simulate`
    """
    to_ret = []
    for command in runlog:
        to_ret.append(
            '\t' * command['level']
            + command['payload'].get('text', '').format(**command['payload']))
        if command['logs']:
            to_ret.append('\t' * command['level'] + 'Logs from this command:')
            to_ret.extend(
                ['\t' * command['level']
                 + f'{l.levelname} ({l.module}): {l.msg}' % l.args
                 for l in command['logs']])
    return '\n'.join(to_ret)


def _get_bundle_args(
        parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument(
        '-L', '--custom-labware-path',
        action='append', default=[os.getcwd()],
        help='Specify directories to search for custom labware definitions. '
             'You can specify this argument multiple times. Once you specify '
             'a directory in this way, labware definitions in that directory '
             'will become available in ProtocolContext.load_labware(). '
             'Bundle execution will still only allow labware defined in '
             'the bundle. Only directories specified directly by '
             'this argument are searched, not their children.')
    parser.add_argument(
        '-D', '--custom-data-path',
        action='append', nargs='?', const='.', default=[],
        help='Specify directories to search for custom data files. '
             'You can specify this argument multiple times. Once you specify '
             'a directory in this way, files located in the specified '
             'directory will be available in ProtocolContext.bundled_data. '
             'Note that bundle execution will still only allow data files in '
             'the bundle. If you specify this without a path, it will '
             'add the current path implicitly. If you do not specify this '
             'argument at all, no data files will be added. Any file in the '
             'specified paths will be loaded into memory and included in the '
             'bundle if --bundle is passed, so be careful that any directory '
             'you specify has only the files you want. It is usually a '
             'better idea to use -d so no files are accidentally included. '
             'Also note that data files are made available as their name, not '
             'their full path, so name them uniquely.')
    parser.add_argument(
        '-d', '--custom-data-file',
        action='append', default=[],
        help='Specify data files to be made available in '
             'ProtocolContext.bundled_data (and possibly bundled if --bundle '
             'is passed). Can be specified multiple times with different '
             'files. It is usually a better idea to use this than -D because '
             'there is less possibility of accidentally including something.')
    parser.add_argument(
        '-b', '--bundle', nargs='?', const='PROTOCOL.ot2.zip', default=None,
        action='store', type=str,
        help='Bundle the specified protocol file, any labware used in it, and '
             'any files in the data directories specified with -D into a '
             'bundle. This bundle can be executed on a robot and carries with '
             'it all the custom labware and data required to run. Without a '
             'value specified in this argument, the bundle will be called '
             '(protocol name without the .py).ot2.zip, but you can specify '
             'a different output name. \n'
             'These bundles are a beta feature, and their behavior may change')
    return parser


def get_arguments(
        parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """ Get the argument parser for this module

    Useful if you want to use this module as a component of another CLI program
    and want to add its arguments.

    :param parser: A parser to add arguments to. If not specified, one will be
                   created.
    :returns argparse.ArgumentParser: The parser with arguments added.
    """
    parser.add_argument(
        '-l', '--log-level',
        choices=['debug', 'info', 'warning', 'error', 'none'],
        default='warning',
        help='Specify the level filter for logs to show on the command line. '
        'Log levels below warning can be chatty. If "none", do not show logs')

    if opentrons.config.feature_flags.use_protocol_api_v2():
        parser = _get_bundle_args(parser)

    parser.add_argument(
        'protocol', metavar='PROTOCOL',
        type=argparse.FileType('rb'),
        help='The protocol file to simulate. If you pass \'-\', you can pipe '
        'the protocol via stdin; this could be useful if you want to use this '
        'utility as part of an automated workflow.')
    parser.add_argument(
        '-v', '--version', action='version',
        version=f'%(prog)s {opentrons.__version__}',
        help='Print the opentrons package version and exit')
    parser.add_argument(
        '-o', '--output', action='store',
        help='What to output during simulations',
        choices=['runlog', 'nothing'],
        default='runlog')
    return parser


def _get_bundle_dest(
        bundle_name: Optional[str],
        default_key: str,
        proto_name: str) -> Optional[BinaryIO]:
    if bundle_name == default_key:
        protopath = pathlib.Path(proto_name)
        # strip all the suffixes since protocols are often named
        # .ot2.zip
        if protopath.name.endswith('.ot2.py'):
            protoname = pathlib.Path(protopath.stem).stem
        else:
            protoname = protopath.stem
        bundle_name = str((pathlib.Path.cwd() / protoname)
                          .with_suffix('.ot2.zip'))
        return open(bundle_name, 'wb')
    elif bundle_name:
        return open(bundle_name, 'wb')
    else:
        return None


# Note - this script is also set up as a setuptools entrypoint and thus does
# an absolute minimum of work since setuptools does something odd generating
# the scripts
def main() -> int:
    """ Run the simulation """
    parser = argparse.ArgumentParser(prog='opentrons_simulate',
                                     description='Simulate an OT-2 protocol')
    parser = get_arguments(parser)

    args = parser.parse_args()
    runlog, maybe_bundle = simulate(
        args.protocol,
        args.protocol.name,
        getattr(args, 'custom_labware_path', []),
        getattr(args, 'custom_data_path', [])
        + getattr(args, 'custom_data_file', []),
        log_level=args.log_level)

    if maybe_bundle:
        bundle_name = getattr(args, 'bundle', None)
        if bundle_name == args.protocol.name:
            raise RuntimeError(
                'Bundle path and input path must be different')
        bundle_dest = _get_bundle_dest(
            bundle_name, 'PROTOCOL.ot2.zip', args.protocol.name)
        if bundle_dest:
            bundle.create_bundle(maybe_bundle, bundle_dest)

    if args.output == 'runlog':
        print(format_runlog(runlog))

    return 0


if __name__ == '__main__':
    sys.exit(main())
