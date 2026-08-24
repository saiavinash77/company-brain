// Design tokens — extracted from munder-difflin DESIGN.md (pixel aesthetic).
// Maroon/gold brand pair per the Company Brain spec; the rest is the
// munder-difflin palette (§3) with status colors from §3.4.

export const COLORS = {
  // brand
  maroonDeep: '#6E1423',
  gold: '#F4D35E',

  // surfaces
  ink: '#1A1423',
  paper: '#F7F2EA',
  panel: '#FFF8EC',
  panelEdge: '#E8DCC8',
  wallTop: '#C9B8A3',
  wallBottom: '#B09A82',

  // floor checkerboard (grass tiles, 32px)
  grassLight: '#9FD08A',
  grassDark: '#8CC178',

  // wood desks
  woodLight: '#D2A25F',
  woodDark: '#B5854A',
  woodShadow: '#8A6435',

  // text
  textPrimary: '#1A1423',
  textSecondary: '#66584A',

  // agent accents (rotated across specialists)
  coral: '#FF6B6B',
  mint: '#6BCF7F',
  sky: '#4ECDC4',
  lemon: '#FFD93D',
  lilac: '#B197FC',
  peach: '#FFA07A',

  // avatar slots
  skin: '#E8B98F',
  hair: '#4A3728',
  outfitBase: '#3D3654',

  // status (DESIGN.md §3.4)
  statusIdle: '#A899B5',
  statusWorking: '#FFD93D',
  statusHandoff: '#4ECDC4',
  statusWaiting: '#6C8EF5',
  statusBlocked: '#FF6B6B',
  statusSuccess: '#6BCF7F',
}

// World size must match backend floor_config FLOOR_META.
export const WORLD = { width: 960, height: 560 }

export const WALK_SPEED = 80 // px/s, per DESIGN.md §8

export function stateColor(state) {
  if (state === 'working') return COLORS.statusWorking
  if (state === 'handoff') return COLORS.statusHandoff
  if (state === 'waiting') return COLORS.statusWaiting
  if (state === 'blocked') return COLORS.statusBlocked
  if (state === 'success') return COLORS.statusSuccess
  return COLORS.statusIdle
}
