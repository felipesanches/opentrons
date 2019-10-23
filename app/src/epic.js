// @flow
// root application epic
import { combineEpics } from 'redux-observable'

import { analyticsEpic } from './analytics'
import { discoveryEpic } from './discovery'
import { robotApiEpic } from './robot-api'
import { robotSettingsEpic } from './robot-settings/epic'
import { shellEpic } from './shell'

export default combineEpics(
  analyticsEpic,
  discoveryEpic,
  robotApiEpic,
  robotSettingsEpic,
  shellEpic
)
