// electron main entry point
import { app, dialog, ipcMain, Menu } from 'electron'

import createUi from './ui'
import initializeMenu from './menu'
import createLogger from './log'
import { getConfig, getStore, getOverrides, registerConfig } from './config'
import { registerDiscovery } from './discovery'
import { registerLabware } from './labware'
import { registerRobotLogs } from './robot-logs'
import { registerUpdate } from './update'
import { registerBuildrootUpdate } from './buildroot'

const config = getConfig()
const log = createLogger(__filename)

log.debug('App config', {
  config,
  store: getStore(),
  overrides: getOverrides(),
})

if (config.devtools) {
  require('electron-debug')({ isEnabled: true, showDevTools: true })
}

// hold on to references so they don't get garbage collected
let mainWindow
let rendererLogger

app.once('ready', startUp)
app.once('window-all-closed', () => app.quit())

function startUp() {
  log.info('Starting App')
  process.on('uncaughtException', error => log.error('Uncaught: ', { error }))

  mainWindow = createUi()
  rendererLogger = createRendererLogger()

  mainWindow.once('closed', () => (mainWindow = null))
  initializeMenu()

  // wire modules to UI dispatches
  const dispatch = action => {
    log.silly('Sending action via IPC to renderer', { action })
    mainWindow.webContents.send('dispatch', action)
  }

  const configHandler = registerConfig(dispatch)
  const discoveryHandler = registerDiscovery(dispatch)
  const labwareHandler = registerLabware(dispatch)
  const robotLogsHandler = registerRobotLogs(dispatch, mainWindow)
  const updateHandler = registerUpdate(dispatch)
  const buildrootUpdateHandler = registerBuildrootUpdate(dispatch)

  ipcMain.on('dispatch', (_, action) => {
    log.debug('Received action via IPC from renderer', { action })
    configHandler(action)
    discoveryHandler(action)
    labwareHandler(action)
    robotLogsHandler(action)
    updateHandler(action)
    buildrootUpdateHandler(action)
  })

  if (config.devtools) {
    installAndOpenExtensions().catch(error =>
      dialog.showErrorBox('Error opening dev tools', error)
    )
  }

  log.silly('Global references', { mainWindow, rendererLogger })
}

function createRendererLogger() {
  log.info('Creating renderer logger')

  const logger = createLogger()
  ipcMain.on('log', (_, info) => logger.log(info))

  return logger
}

function installAndOpenExtensions() {
  const devtools = require('electron-devtools-installer')
  const forceDownload = !!process.env.UPGRADE_EXTENSIONS
  const install = devtools.default
  const extensions = ['REACT_DEVELOPER_TOOLS', 'REDUX_DEVTOOLS']

  return Promise.all(
    extensions.map(name => install(devtools[name], forceDownload))
  ).then(() =>
    mainWindow.webContents.on('context-menu', (_, props) => {
      const { x, y } = props

      Menu.buildFromTemplate([
        {
          label: 'Inspect element',
          click: () => mainWindow.inspectElement(x, y),
        },
      ]).popup(mainWindow)
    })
  )
}
