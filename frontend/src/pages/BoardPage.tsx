import React, { useCallback, useEffect, useMemo, useState } from "react"
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core"
import { useAuth } from "../context/AuthContext"
import Column from "../components/Column"
import TaskCard from "../components/TaskCard"
import CreateTaskModal from "../components/CreateTaskModal"
import {
  getTasks,
  startTask,
  completeTask,
  UnauthorizedError,
  type Task,
  type TaskStatus,
} from "../lib/apiClient"
import { runWithSpan } from "../telemetry"

// ─── Types ────────────────────────────────────────────────────────────────
type TransitionAction = "start" | "complete"

/** Valid drag-and-drop transitions between columns. */
const TRANSITIONS: Partial<Record<TaskStatus, Partial<Record<TaskStatus, TransitionAction>>>> = {
  created:     { in_progress: "start"    },
  in_progress: { completed:   "complete" },
}

interface ColumnConfig {
  id: TaskStatus
  label: string
  dotColor: string
}

const COLUMNS: ColumnConfig[] = [
  { id: "created",     label: "Created",     dotColor: "var(--col-created)"     },
  { id: "in_progress", label: "In Progress", dotColor: "var(--col-in-progress)" },
  { id: "completed",   label: "Completed",   dotColor: "var(--col-completed)"   },
]

// ─── Component ────────────────────────────────────────────────────────────
export default function BoardPage(): React.JSX.Element {
  const { user, logout, handleUnauthorized } = useAuth()

  const [tasks, setTasks]           = useState<Task[]>([])
  const [loading, setLoading]       = useState(true)
  const [boardError, setBoardError] = useState("")
  const [showModal, setShowModal]   = useState(false)
  const [activeTask, setActiveTask] = useState<Task | null>(null)

  const sensors = useSensors(
    useSensor(PointerSensor, {
      // Require 5 px of movement before a drag starts so normal clicks work.
      activationConstraint: { distance: 5 },
    })
  )

  const loadTasks = useCallback(async (): Promise<void> => {
    setLoading(true)
    setBoardError("")
    try {
      const data = await getTasks()
      setTasks(data)
    } catch (err) {
      if (err instanceof UnauthorizedError) {
        handleUnauthorized()
      } else {
        setBoardError(err instanceof Error ? err.message : "Failed to load tasks.")
      }
    } finally {
      setLoading(false)
    }
  }, [handleUnauthorized])

  useEffect(() => { void loadTasks() }, [loadTasks])

  const tasksByStatus = useMemo(
    (): Record<TaskStatus, Task[]> => ({
      created:     tasks.filter(t => t.status === "created"),
      in_progress: tasks.filter(t => t.status === "in_progress"),
      completed:   tasks.filter(t => t.status === "completed"),
    }),
    [tasks]
  )

  // ─── Drag handlers ────────────────────────────────────────────────────────
  function handleDragStart({ active }: DragStartEvent): void {
    setActiveTask(tasks.find(t => t.id === String(active.id)) ?? null)
  }

  async function handleDragEnd({ active, over }: DragEndEvent): Promise<void> {
    setActiveTask(null)
    if (!over) return

    const task      = tasks.find(t => t.id === String(active.id))
    const targetCol = String(over.id) as TaskStatus

    if (!task || task.status === targetCol) return

    const action = TRANSITIONS[task.status]?.[targetCol]
    if (!action) return  // invalid transition — card snaps back

    // Optimistically update so the UI responds immediately.
    setTasks(prev => prev.map(t => t.id === task.id ? { ...t, status: targetCol } : t))

    try {
      const updated = await runWithSpan(
        "tasks.move",
        async () =>
          action === "start"
            ? startTask(task.id)
            : completeTask(task.id),
        {
          "task.transition": action,
          "task.status.from": task.status,
          "task.status.to": targetCol,
        }
      )

      setTasks(prev => prev.map(t => t.id === updated.id ? updated : t))
    } catch (err) {
      // Revert the optimistic update on failure.
      setTasks(prev => prev.map(t => t.id === task.id ? task : t))

      if (err instanceof UnauthorizedError) {
        handleUnauthorized()
      } else {
        setBoardError(err instanceof Error ? err.message : "Failed to update task.")
      }
    }
  }

  function handleTaskCreated(newTask: Task): void {
    setTasks(prev => [newTask, ...prev])
    setShowModal(false)
  }

  return (
    <div className="app-shell">
      {/* ── Top bar ──────────────────────────────────────────────────────── */}
      <header className="topbar">
        <span className="topbar__brand">SaaS Debug Lab</span>
        <div className="topbar__right">
          {user && (
            <span className="topbar__user">
              {user.username} · <em>{user.role}</em>
            </span>
          )}
          <button className="btn btn--ghost btn--sm" onClick={logout}>
            Sign out
          </button>
        </div>
      </header>

      {/* ── Board ────────────────────────────────────────────────────────── */}
      <main className="board-container">
        <div className="board-toolbar">
          <h1 className="board-toolbar__title">Task Board</h1>
          <button className="btn btn--primary" onClick={() => setShowModal(true)}>
            + New Task
          </button>
        </div>

        {boardError && (
          <div className="board-error">
            {boardError}
            <button
              className="btn btn--ghost btn--sm"
              onClick={() => setBoardError("")}
            >
              ✕
            </button>
          </div>
        )}

        {loading ? (
          <div className="loading-center">
            <span className="spinner" />
            Loading tasks…
          </div>
        ) : (
          <DndContext
            sensors={sensors}
            onDragStart={handleDragStart}
            onDragEnd={handleDragEnd}
          >
            <div className="board">
              {COLUMNS.map(col => (
                <Column
                  key={col.id}
                  id={col.id}
                  label={col.label}
                  dotColor={col.dotColor}
                  tasks={tasksByStatus[col.id]}
                />
              ))}
            </div>

            <DragOverlay>
              {activeTask ? <TaskCard task={activeTask} isOverlay /> : null}
            </DragOverlay>
          </DndContext>
        )}
      </main>

      {showModal && (
        <CreateTaskModal
          onCreated={handleTaskCreated}
          onClose={() => setShowModal(false)}
          onUnauthorized={handleUnauthorized}
        />
      )}
    </div>
  )
}
