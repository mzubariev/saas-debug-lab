import React from "react"
import { useDraggable } from "@dnd-kit/core"
import { type Task } from "../lib/apiClient"

interface TaskCardProps {
  task: Task
  /** True when rendered inside DragOverlay (follows cursor, no transform). */
  isOverlay?: boolean
}

function formatDate(iso: string | undefined): string {
  if (!iso) return ""
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" })
}

export default function TaskCard({ task, isOverlay = false }: TaskCardProps): React.JSX.Element {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: task.id,
    data: { task },
  })

  const classes = [
    "task-card",
    isDragging ? "task-card--dragging" : "",
    isOverlay  ? "task-card--overlay"  : "",
  ]
    .filter(Boolean)
    .join(" ")

  // The overlay card (in DragOverlay) has no ref / listeners — it just renders.
  return (
    <div
      ref={isOverlay ? undefined : setNodeRef}
      className={classes}
      {...(isOverlay ? {} : { ...listeners, ...attributes })}
    >
      <p className="task-card__title">{task.title}</p>
      <div className="task-card__meta">
        <span className="task-card__id" title={task.id}>
          #{task.id.slice(0, 8)}
        </span>
        <span className="task-card__date">{formatDate(task.created_at)}</span>
      </div>
    </div>
  )
}
