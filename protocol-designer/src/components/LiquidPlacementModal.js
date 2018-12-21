// @flow
import * as React from 'react'
import {connect} from 'react-redux'
import type {Dispatch} from 'redux'
import cx from 'classnames'
import isEmpty from 'lodash/isEmpty'
import omit from 'lodash/omit'

import styles from './LiquidPlacementModal.css'

import type {Wells, ContentsByWell} from '../labware-ingred/types'
import {SelectableLabware} from '../components/labware'
import LiquidPlacementForm from '../components/LiquidPlacementForm'
import SingleLabwareWrapper from '../components/SingleLabware'
import WellSelectionInstructions from './WellSelectionInstructions'

import {selectors} from '../labware-ingred/reducers'
import * as wellContentsSelectors from '../top-selectors/well-contents'

import type {BaseState} from '../types'
import type {WellIngredientNames} from '../steplist'

type SP = {
  selectedWells: Wells,
  wellContents: ContentsByWell,
  containerType: string,
  liquidNamesById: WellIngredientNames,
}

type State = {
  highlightedWells: Wells,
  selectedWells: Wells,
}

class LiquidPlacementModal extends React.Component<SP, State> {
  state = {highlightedWells: {}, selectedWells: {}}

  updateHighlightedWells = (wells: Wells) => {
    this.setState({highlightedWells: wells})
  }

  selectWells = (wells: Wells) => {
    this.setState({selectedWells: {...this.state.selectedWells, ...wells}})
  }
  deselectWells = (wells: Wells) => {
    this.setState({selectedWells: omit(this.state.selectedWells, Object.keys(wells))})
  }
  deselectAll = () => {
    this.setState({selectedWells: {}})
  }

  render () {
    const {wellContents} = this.props
    const {selectedWells} = this.state
    let commonSelectedLiquidId = null

    if (!isEmpty(wellContents) && !isEmpty(selectedWells)) {
      const firstSelectedWell = Object.keys(selectedWells)[0]
      const liquidIds = wellContents[firstSelectedWell] ? Object.keys(wellContents[firstSelectedWell].ingreds) : []
      const firstSelectedLiquidId = liquidIds[0] || null
      const hasCommonSelectedLiquidId = Object.keys(selectedWells).every(well => {
        const ingreds = wellContents[well].ingreds ? Object.keys(wellContents[well].ingreds) : []
        return ingreds.length === 1 && ingreds[0] === firstSelectedLiquidId
      })
      commonSelectedLiquidId = hasCommonSelectedLiquidId ? firstSelectedLiquidId : null
    }

    return (
      <div className={cx(styles.liquid_placement_modal, {[styles.expanded]: !isEmpty(selectedWells)})}>
        <LiquidPlacementForm
          commonSelectedLiquidId={commonSelectedLiquidId}
          // initialVolume={commonSelectedLiquidId}
          deselectAll={this.deselectAll}
          selectedWells={selectedWells} />

        <SingleLabwareWrapper showLabels>
          <SelectableLabware
            wellContents={this.props.wellContents}
            containerType={this.props.containerType}
            selectedWells={selectedWells}
            highlightedWells={this.state.highlightedWells}
            selectWells={this.selectWells}
            deselectWells={this.deselectWells}
            updateHighlightedWells={this.updateHighlightedWells}
            ingredNames={this.props.liquidNamesById} />
        </SingleLabwareWrapper>

        <WellSelectionInstructions />
      </div>
    )
  }
}

const mapStateToProps = (state: BaseState): SP => {
  const containerId = selectors.getSelectedLabwareId(state)
  if (containerId === null) {
    console.error('LiquidPlacementModal: No labware is selected, and no labwareId was given to LiquidPlacementModal')
    return {wellContents: {}, containerType: '', liquidNamesById: {}}
  }

  const labware = selectors.getLabwareById(state)[containerId]
  let wellContents: ContentsByWell = {}

  // selection for deck setup: shows initial state of liquids
  wellContents = wellContentsSelectors.getWellContentsAllLabware(state)[containerId]

  return {
    wellContents,
    containerType: labware ? labware.type : 'missing labware',
    liquidNamesById: selectors.getLiquidNamesById(state),
  }
}

export default connect(mapStateToProps)(LiquidPlacementModal)
