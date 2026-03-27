import React, { useEffect, useRef, useState } from "react"
import { createTask, UnauthorizedError, type Task } from "../lib/apiClient"
import { runWithSpan } from "../telemetry"

interface CreateTaskModalProps {
  onCreated: (task: Task) => void
  onClose: () => void
  onUnauthorized: () => void
}

export default function CreateTaskModal({
  onCreated,
  onClose,
  onUnauthorized,
}: CreateTaskModalProps): React.JSX.Element {
  const [title, setTitle]     = useState("")
  const [error, setError]     = useState("")
  const [loading, setLoading] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => { inputRef.current?.focus() }, [])

  useEffect(() => {
    function handleKey(e: KeyboardEvent): void {
      if (e.key === "Escape") onClose()
    }
    document.addEventListener("keydown", handleKey)
    return () => document.removeEventListener("keydown", handleKey)
  }, [onClose])

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault()
    const trimmed = title.trim()
    if (!trimmed) return

    setError("")
    setLoading(true)
    try {
      const task = await runWithSpan("tasks.create", async _span =>
        createTask(trimmed)
      )
      onCreated(task)
    } catch (err) {
      if (err instanceof UnauthorizedError) {
        onUnauthorized()
      } else {
        setError(err instanceof Error ? err.message : "Failed to create task.")
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      className="modal-backdrop"
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
        <h2 className="modal__title" id="modal-title">Create task</h2>

        {error && <div className="alert alert--error">{error}</div>}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="task-title">Title</label>
            <input
              ref={inputRef}
              id="task-title"
              className="form-control"
              type="text"
              value={title}
              onChange={e => setTitle(e.target.value)}
              placeholder="Describe the task…"
              maxLength={200}
              required
            />
          </div>

          <div className="modal__footer">
            <button
              type="button"
              className="btn btn--ghost"
              onClick={onClose}
              disabled={loading}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn btn--primary"
              disabled={loading || !title.trim()}
            >
              {loading ? (
                <><span className="spinner" style={{ width: 14, height: 14 }} /> Creating…</>
              ) : (
                "Create task"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
