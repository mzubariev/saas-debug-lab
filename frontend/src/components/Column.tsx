import React, { useState } from "react"
import { useDroppable } from "@dnd-kit/core"
import TaskCard from "./TaskCard"
import { type Task, type TaskStatus } from "../lib/apiClient"

interface ColumnProps {
  id: TaskStatus
  label: string
  dotColor: string
  tasks: Task[]
}

const PAGE_SIZE = 10

export default function Column({ id, label, dotColor, tasks }: ColumnProps): React.JSX.Element {
  const { setNodeRef, isOver } = useDroppable({ id })
  const [page, setPage] = useState(1)

  const totalPages  = Math.max(1, Math.ceil(tasks.length / PAGE_SIZE))
  // Clamp current page when the task list shrinks (e.g. after a drag-out).
  const safePage    = Math.min(page, totalPages)
  const visibleTasks = tasks.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE)

  return (
    <div
      ref={setNodeRef}
      className={`column${isOver ? " column--over" : ""}`}
    >
      {/* Header */}
      <div className="column__header">
        <span className="column__title">
          <span className="column__dot" style={{ background: dotColor }} />
          {label}
        </span>
        <span className="column__count">{tasks.length}</span>
      </div>

      {/* Task list */}
      <div className="column__body">
        {visibleTasks.length === 0 ? (
          <p className="column__empty">No tasks here</p>
        ) : (
          visibleTasks.map(task => (
            <TaskCard key={task.id} task={task} />
          ))
        )}
      </div>

      {/* Per-column pagination — only shown when there are multiple pages */}
      {totalPages > 1 && (
        <div className="column__pagination">
          <button
            className="btn btn--ghost btn--sm"
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={safePage === 1}
          >
            ←
          </button>
          <span>{safePage} / {totalPages}</span>
          <button
            className="btn btn--ghost btn--sm"
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            disabled={safePage === totalPages}
          >
            →
          </button>
        </div>
      )}
    </div>
  )
}
