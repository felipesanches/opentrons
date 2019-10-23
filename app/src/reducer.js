// @flow
import createHistory from 'history/createHashHistory'
import { connectRouter } from 'connected-react-router'

// interface state
import { combineReducers } from 'redux'

// oldest robot api state
import { robotReducer } from './robot'

// old api state
import { reducer as apiReducer } from './http-api-client'

// api state
import { robotApiReducer } from './robot-api'

// robot settings state
import { robotSettingsReducer } from './robot-settings/reducer'

// app shell state
import { shellReducer } from './shell'

// config state
import { configReducer } from './config'

// discovery state
import { discoveryReducer } from './discovery'

// protocol state
import { protocolReducer } from './protocol'

import type { Reducer } from 'redux'
import type { State, Action } from './types'

export const history = createHistory()

const rootReducer: Reducer<State, Action> = combineReducers<_, Action>({
  robot: robotReducer,
  api: apiReducer,
  robotApi: robotApiReducer,
  robotSettings: robotSettingsReducer,
  config: configReducer,
  discovery: discoveryReducer,
  protocol: protocolReducer,
  shell: shellReducer,
  router: connectRouter<_, Action>(history),
})

export default rootReducer
