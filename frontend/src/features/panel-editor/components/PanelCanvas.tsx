import type Konva from 'konva'
import { useEffect, useRef, type KeyboardEvent } from 'react'
import { Image as KImage, Layer, Rect, Stage, Transformer } from 'react-konva'
import type { Mask } from '../../../shared/api/types'
import { useElementWidth } from '../../../shared/hooks/useElementWidth'
import { useHtmlImage } from '../../../shared/hooks/useHtmlImage'
import { NO_MOVE, type Move } from '../store'

export interface PanelCanvasProps {
  imageSrc: string
  panelSize: { width: number; height: number }
  /** Masks with a move, drawn at their new place (holes where they were). */
  moved: { mask: Mask; cutoutSrc: string | null; move: Move }[]
  selected: { mask: Mask; cutoutSrc: string | null; move: Move } | null
  busy: boolean
  onPick: (point: { x: number; y: number }, preview: { width: number; height: number }) => void
  onSelectMask: (mask: Mask) => void
  onMove: (mask: Mask, move: Move) => void
}

const BLUE = '#4F8FD0'
const NUDGE = 10 // panel pixels per arrow press; Shift for 50

function CutOut({
  mask,
  src,
  move,
  k,
  selected,
  onSelect,
  onMove,
  transformer,
}: {
  mask: Mask
  src: string | null
  move: Move
  k: number
  selected: boolean
  onSelect: () => void
  onMove: (move: Move) => void
  transformer: React.RefObject<Konva.Transformer | null>
}) {
  const image = useHtmlImage(src)
  const node = useRef<Konva.Image>(null)
  const { left, top, right, bottom } = mask.box
  useEffect(() => {
    if (selected && node.current && transformer.current) {
      transformer.current.nodes([node.current])
      transformer.current.getLayer()?.batchDraw()
    }
  }, [selected, image, transformer])
  if (!image) return null
  const read = (n: Konva.Image): Move => ({ dx: n.x() / k - left, dy: n.y() / k - top, scale: n.scaleX() })
  return (
    <KImage
      ref={node}
      image={image}
      x={(left + move.dx) * k}
      y={(top + move.dy) * k}
      width={(right - left) * k}
      height={(bottom - top) * k}
      scaleX={move.scale}
      scaleY={move.scale}
      draggable={selected}
      shadowColor={selected ? BLUE : undefined}
      shadowBlur={selected ? 14 : 0}
      shadowOpacity={selected ? 1 : 0}
      onClick={(e) => {
        e.cancelBubble = true
        onSelect()
      }}
      onTap={(e) => {
        e.cancelBubble = true
        onSelect()
      }}
      onDragEnd={(e) => onMove(read(e.target as Konva.Image))}
      onTransformEnd={(e) => {
        const n = e.target as Konva.Image
        onMove(read(n))
      }}
    />
  )
}

/** Where a moved cut-out came from: erased from the panel, so a move looks like a move, not a copy. */
function Hole({ mask, src, k }: { mask: Mask; src: string | null; k: number }) {
  const image = useHtmlImage(src)
  if (!image) return null
  const { left, top, right, bottom } = mask.box
  return <KImage image={image} x={left * k} y={top * k} width={(right - left) * k} height={(bottom - top) * k} globalCompositeOperation="destination-out" listening={false} />
}

export function PanelCanvas({ imageSrc, panelSize, moved, selected, busy, onPick, onSelectMask, onMove }: PanelCanvasProps) {
  const box = useRef<HTMLDivElement>(null)
  const width = useElementWidth(box)
  const height = Math.round((width * panelSize.height) / panelSize.width)
  const k = width / panelSize.width
  const base = useHtmlImage(imageSrc)
  const transformer = useRef<Konva.Transformer>(null)

  const layers = new Map(moved.map((m) => [m.mask.id, m]))
  if (selected) layers.set(selected.mask.id, selected)

  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (!selected) return
    const step = e.shiftKey ? NUDGE * 5 : NUDGE
    const m = selected.move
    const next: Partial<Record<string, Move>> = {
      ArrowLeft: { ...m, dx: m.dx - step },
      ArrowRight: { ...m, dx: m.dx + step },
      ArrowUp: { ...m, dy: m.dy - step },
      ArrowDown: { ...m, dy: m.dy + step },
      '+': { ...m, scale: m.scale * 1.1 },
      '=': { ...m, scale: m.scale * 1.1 },
      '-': { ...m, scale: m.scale / 1.1 },
      '0': NO_MOVE,
    }
    const move = next[e.key]
    if (move) {
      e.preventDefault()
      onMove(selected.mask, move)
    }
  }

  return (
    <div
      ref={box}
      tabIndex={0}
      role="application"
      aria-label="Panel canvas. Click an object to select it. With one selected, arrow keys move it, plus and minus resize it, 0 puts it back."
      onKeyDown={onKey}
      className="frame w-full"
      style={{ aspectRatio: `${panelSize.width} / ${panelSize.height}`, cursor: busy ? 'progress' : 'crosshair' }}
      data-testid="panel-canvas"
    >
      {width > 0 && base && (
        <Stage
          width={width}
          height={height}
          onClick={(e) => {
            const pos = e.target.getStage()?.getPointerPosition()
            if (pos && !busy) onPick(pos, { width, height })
          }}
          onTap={(e) => {
            const pos = e.target.getStage()?.getPointerPosition()
            if (pos && !busy) onPick(pos, { width, height })
          }}
        >
          <Layer>
            <KImage image={base} width={width} height={height} />
            {[...layers.values()]
              .filter((m) => m.move.dx || m.move.dy || m.move.scale !== 1)
              .map((m) => (
                <Hole key={m.mask.id} mask={m.mask} src={m.cutoutSrc} k={k} />
              ))}
          </Layer>
          <Layer>
            {[...layers.values()].map((m) => (
              <CutOut
                key={m.mask.id}
                mask={m.mask}
                src={m.cutoutSrc}
                move={m.move}
                k={k}
                selected={selected?.mask.id === m.mask.id}
                onSelect={() => onSelectMask(m.mask)}
                onMove={(move) => onMove(m.mask, move)}
                transformer={transformer}
              />
            ))}
            {selected && (
              <Rect
                x={(selected.mask.box.left + selected.move.dx) * k}
                y={(selected.mask.box.top + selected.move.dy) * k}
                width={(selected.mask.box.right - selected.mask.box.left) * k * selected.move.scale}
                height={(selected.mask.box.bottom - selected.mask.box.top) * k * selected.move.scale}
                stroke={BLUE}
                strokeWidth={1.5}
                dash={[6, 4]}
                listening={false}
              />
            )}
            {selected && <Transformer ref={transformer} rotateEnabled={false} keepRatio enabledAnchors={['top-left', 'top-right', 'bottom-left', 'bottom-right']} borderStroke={BLUE} anchorStroke={BLUE} anchorFill="#F2C230" />}
          </Layer>
        </Stage>
      )}
    </div>
  )
}
