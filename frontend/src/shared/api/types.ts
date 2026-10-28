import type { components } from './schema'

type Schemas = components['schemas']

export type Project = Schemas['ProjectOut']
export type Shot = Schemas['ShotOut']
export type Panel = Schemas['PanelOut']
export type Mask = Schemas['MaskOut']
export type Character = Schemas['CharacterOut']
export type Turn = Schemas['TurnOut']
export type Ticket = Schemas['TicketOut']
export type Selection = Schemas['SelectionOut']
export type CastReview = Schemas['CastReviewOut']
export type PanelStyle = Schemas['ProjectCreate']['style']
