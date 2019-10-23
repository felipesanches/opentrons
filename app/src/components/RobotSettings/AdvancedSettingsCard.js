// @flow
// app info card with version and updated
import * as React from 'react'
import { useSelector, useDispatch } from 'react-redux'
import { Link } from 'react-router-dom'

import {
  fetchSettings,
  updateSetting,
  clearRestartRequired,
  getRobotSettings,
  getRobotRestartRequired,
} from '../../robot-settings'

import { CONNECTABLE } from '../../discovery'
import { restartRobotServer } from '../../http-api-client/server'
import { downloadLogs } from '../../shell/robot-logs/actions'
import { getRobotLogsDownloading } from '../../shell/robot-logs/selectors'
import { Portal } from '../portal'
import {
  AlertModal,
  Card,
  LabeledButton,
  LabeledToggle,
  Icon,
} from '@opentrons/components'

import type { State, Dispatch } from '../../types'
import type { ViewableRobot } from '../../discovery/types'
import type { RobotSettings } from '../../robot-settings/types'

import UploadRobotUpdate from './UploadRobotUpdate'

type Props = {|
  robot: ViewableRobot,
  resetUrl: string,
|}

const TITLE = 'Advanced Settings'
const ROBOT_LOGS_OPTOUT_ID = 'disableLogAggregation'

const ROBOT_LOGS_OUTOUT_HEADING = 'Robot Logging'
const ROBOT_LOGS_OPTOUT_MESSAGE = (
  <>
    <p>
      If your OT-2 is connected to the internet, Opentrons will collect logs
      from your robot to troubleshoot issues and identify error trends.
    </p>
    <p>
      If you would like to disable log collection, please click &quot;Opt
      out&quot; below.
    </p>
  </>
)

const RESTART_REQUIRED_HEADING = 'Robot Restart Required'
const RESTART_REQUIRED_MESSAGE = (
  <p>
    You must restart your robot for this setting change to take effect. Would
    you like to restart now?
  </p>
)

export default function AdvancedSettingsCard(props: Props) {
  const { robot, resetUrl } = props
  const { name, health, status } = robot
  const settings = useSelector<State, RobotSettings>(state =>
    getRobotSettings(state, name)
  )
  const restartRequired = useSelector<State, boolean>(state =>
    getRobotRestartRequired(state, name)
  )
  const robotLogsDownloading = useSelector(getRobotLogsDownloading)
  const dispatch = useDispatch<Dispatch>()
  const disabled = status !== CONNECTABLE
  const logsAvailable = health && health.logs

  const showLogOptoutModal = settings.some(
    s => s.id === ROBOT_LOGS_OPTOUT_ID && s.value === null
  )
  const setLogOptout = (value: boolean) =>
    dispatch(updateSetting(robot, ROBOT_LOGS_OPTOUT_ID, value))

  const clearRestartAlert = () => dispatch(clearRestartRequired(name))
  const restart = () => {
    dispatch(restartRobotServer(robot))
    clearRestartAlert()
  }

  React.useEffect(() => {
    dispatch(fetchSettings(robot))
  }, [dispatch, robot])

  return (
    <Card title={TITLE} disabled={disabled}>
      <LabeledButton
        label="Download Logs"
        buttonProps={{
          children: robotLogsDownloading ? (
            <Icon name="ot-spinner" height="1em" spin />
          ) : (
            'Download'
          ),
          disabled: disabled || !logsAvailable || robotLogsDownloading,
          onClick: () => dispatch(downloadLogs(robot)),
        }}
      >
        <p>Access logs from this robot.</p>
      </LabeledButton>
      <LabeledButton
        label="Factory Reset"
        buttonProps={{
          disabled,
          Component: Link,
          to: resetUrl,
          children: 'Reset',
        }}
      >
        <p>Restore robot to factory configuration</p>
      </LabeledButton>
      {settings.map(({ id, title, description, value }) => (
        <LabeledToggle
          key={id}
          label={title}
          toggledOn={value === true}
          onClick={() => dispatch(updateSetting(robot, id, !value))}
        >
          <p>{description}</p>
        </LabeledToggle>
      ))}
      <UploadRobotUpdate robotName={robot.name} />
      {showLogOptoutModal && (
        <Portal>
          <AlertModal
            alertOverlay
            heading={ROBOT_LOGS_OUTOUT_HEADING}
            buttons={[
              { children: 'Opt out', onClick: () => setLogOptout(true) },
              { children: 'Sounds Good!', onClick: () => setLogOptout(false) },
            ]}
          >
            {ROBOT_LOGS_OPTOUT_MESSAGE}
          </AlertModal>
        </Portal>
      )}
      {restartRequired && (
        <Portal>
          <AlertModal
            alertOverlay
            heading={RESTART_REQUIRED_HEADING}
            buttons={[
              { children: 'Now now', onClick: () => clearRestartAlert() },
              { children: 'Restart', onClick: restart },
            ]}
          >
            {RESTART_REQUIRED_MESSAGE}
          </AlertModal>
        </Portal>
      )}
    </Card>
  )
}
