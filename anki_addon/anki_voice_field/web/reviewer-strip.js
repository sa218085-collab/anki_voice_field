(function () {
  "use strict";

  function byId(id) {
    return document.getElementById(id);
  }

  window.avfSetState = function (state) {
    const strip = byId("avf-strip");
    if (!strip) {
      return;
    }

    strip.className = "avf-state-" + String(state.phase || "offline");
    const record = byId("avf-record");
    const label = byId("avf-record-label");
    const status = byId("avf-status");
    const field = byId("avf-field");
    const queue = byId("avf-queue");
    const review = byId("avf-review");
    const action = byId("avf-action");

    label.textContent = String(state.button_label || "Record");
    record.disabled = Boolean(state.button_disabled);
    record.setAttribute(
      "aria-label",
      (state.recording ? "Stop" : "Start") + " voice recording (F8)"
    );
    status.textContent = String(state.status || "Ready.");
    field.textContent = state.field_available
      ? "To: " + String(state.field || "")
      : String(state.field || "No target field");
    field.title = String(state.field || "Destination field unavailable");
    queue.textContent = "Queue " + Number(state.queue_count || 0);
    review.checked = Boolean(state.review_before_save);

    const actionLabel = String(state.action_label || "");
    action.hidden = !actionLabel;
    action.textContent = actionLabel;
  };
})();
