/**
 * Imperative dialog API — call from anywhere without needing component state.
 *
 * Usage:
 *   showError('Title', 'Something went wrong')
 *   showSuccess('Done', 'Lead saved successfully')
 *   showWarning('Required', 'Enter a search query')
 *   showInfo('Note', 'Contact your admin')
 *   showConfirm('Delete?', 'This cannot be undone', () => doDelete())
 *   showDialog({ title, message, type, buttons })
 *
 * Mount <AppDialog /> once in App.js to activate.
 */

let _show = null;

export function _registerDialog(fn) {
  _show = fn;
}

export function showDialog({ title = '', message = '', type = 'info', buttons = null }) {
  if (!_show) return;
  _show({ title, message, type, buttons: buttons || [{ text: 'OK' }] });
}

export function showError(title, message) {
  showDialog({ title, message, type: 'error', buttons: [{ text: 'OK' }] });
}

export function showSuccess(title, message) {
  showDialog({ title, message, type: 'success', buttons: [{ text: 'OK' }] });
}

export function showWarning(title, message) {
  showDialog({ title, message, type: 'warning', buttons: [{ text: 'OK' }] });
}

export function showInfo(title, message) {
  showDialog({ title, message, type: 'info', buttons: [{ text: 'OK' }] });
}

/**
 * @param {string}   title
 * @param {string}   message
 * @param {Function} onConfirm
 * @param {Function} [onCancel]
 * @param {string}   [confirmText]
 * @param {string}   [cancelText]
 * @param {'danger'|'primary'} [confirmStyle]
 */
export function showConfirm(
  title,
  message,
  onConfirm,
  onCancel,
  confirmText = 'Confirm',
  cancelText  = 'Cancel',
  confirmStyle = 'primary',
) {
  showDialog({
    title,
    message,
    type: 'confirm',
    buttons: [
      { text: cancelText,  style: 'cancel',   onPress: onCancel },
      { text: confirmText, style: confirmStyle, onPress: onConfirm },
    ],
  });
}
