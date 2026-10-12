import React, { useEffect } from "react";
import { IconAlert, IconTrash, IconClose } from "./Icons";

export default function ConfirmModal({
  isOpen,
  title = "Are you sure?",
  message = "This action cannot be undone.",
  confirmText = "Delete",
  cancelText = "Cancel",
  isDanger = true,
  loading = false,
  onConfirm,
  onCancel,
}) {
  useEffect(() => {
    function handleKeyDown(event) {
      if (event.key === "Escape" && isOpen && !loading) {
        onCancel();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, loading, onCancel]);

  if (!isOpen) return null;

  return (
    <div className="modal-backdrop" onClick={loading ? undefined : onCancel}>
      <div
        className="modal-card"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <button
          className="modal-close-button"
          onClick={onCancel}
          disabled={loading}
          aria-label="Close dialog"
        >
          <IconClose size={18} />
        </button>

        <div className="modal-header">
          <div className={`modal-icon-badge ${isDanger ? "badge-danger" : "badge-info"}`}>
            {isDanger ? <IconTrash size={22} /> : <IconAlert size={22} />}
          </div>
          <div>
            <h3 className="modal-title">{title}</h3>
            <p className="modal-message">{message}</p>
          </div>
        </div>

        <div className="modal-actions">
          <button
            type="button"
            className="secondary-button"
            onClick={onCancel}
            disabled={loading}
          >
            {cancelText}
          </button>
          <button
            type="button"
            className={`primary-button ${isDanger ? "danger-button" : ""}`}
            onClick={onConfirm}
            disabled={loading}
          >
            {loading ? "Deleting..." : confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}
