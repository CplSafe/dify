import ELK from 'elkjs/lib/elk.bundled.js'

/**
 * Lightweight ELK wrapper for the canvas runtime.
 *
 * Editor-side layout (`workflow/utils/elk-layout.ts`) is heavyweight —
 * it knows about iteration/loop containers, branching node types, and
 * the editor's CUSTOM_NODE shape. The runtime canvas only ever renders
 * a flat list of "runtime" nodes, so we want a much thinner wrapper:
 *
 *   - input:  arrays of `{id}` and `{source, target}`
 *   - output: `Map<id, {x, y}>` with origin normalised to (0, 0)
 *
 * Algorithm: ELK's `layered` (Sugiyama-style) — same family as dagre.
 * Direction RIGHT, balanced node placement, splines edge routing.
 * Spacing tuned for our 280×224 cards with breathing room.
 */
const elk = new ELK()

const LAYOUT_OPTIONS = {
  'elk.algorithm': 'layered',
  'elk.direction': 'RIGHT',
  'elk.layered.spacing.nodeNodeBetweenLayers': '90',
  'elk.spacing.nodeNode': '60',
  'elk.layered.nodePlacement.strategy': 'BRANDES_KOEPF',
  'elk.layered.nodePlacement.bk.fixedAlignment': 'BALANCED',
  'elk.layered.crossingMinimization.strategy': 'LAYER_SWEEP',
  'elk.layered.cycleBreaking.strategy': 'DEPTH_FIRST',
  'elk.edgeRouting': 'SPLINES',
  'elk.separateConnectedComponents': 'true',
  'elk.spacing.componentComponent': '80',
}

export type RuntimeLayoutInput = {
  nodes: Array<{ id: string }>
  edges: Array<{ id: string, source: string, target: string }>
  nodeWidth: number
  nodeHeight: number
}

export type RuntimeLayoutResult = Map<string, { x: number, y: number }>

export const computeRuntimeLayout = async (
  input: RuntimeLayoutInput,
): Promise<RuntimeLayoutResult> => {
  const { nodes, edges, nodeWidth, nodeHeight } = input

  // Empty graphs: bail early — ELK errors on `children: []`.
  if (nodes.length === 0)
    return new Map()

  const graph = {
    id: 'runtime-root',
    layoutOptions: LAYOUT_OPTIONS,
    children: nodes.map(n => ({
      id: n.id,
      width: nodeWidth,
      height: nodeHeight,
    })),
    // Drop edges that reference nodes not in the current set so ELK
    // doesn't choke on dangling references during a partial reveal.
    edges: edges
      .filter((e) => {
        const ids = new Set(nodes.map(n => n.id))
        return ids.has(e.source) && ids.has(e.target)
      })
      .map(e => ({
        id: e.id,
        sources: [e.source],
        targets: [e.target],
      })),
  }

  const layouted = await elk.layout(graph)

  let minX = Number.POSITIVE_INFINITY
  let minY = Number.POSITIVE_INFINITY
  for (const c of layouted.children ?? []) {
    if (typeof c.x === 'number')
      minX = Math.min(minX, c.x)
    if (typeof c.y === 'number')
      minY = Math.min(minY, c.y)
  }
  if (!Number.isFinite(minX))
    minX = 0
  if (!Number.isFinite(minY))
    minY = 0

  const out: RuntimeLayoutResult = new Map()
  for (const c of layouted.children ?? []) {
    out.set(c.id, {
      x: (c.x ?? 0) - minX,
      y: (c.y ?? 0) - minY,
    })
  }
  return out
}
