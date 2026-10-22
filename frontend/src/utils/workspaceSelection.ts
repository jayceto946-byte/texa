const editable = 'input,textarea,select,[contenteditable="true"],math-field';
const reading = '.markdown-body,.workspace-reading-content,.note-reading,.note-document-title,.note-abstract,.goal-objective,pre';

/** Keep Select All inside the current editor or reading block. */
export function selectWorkspaceContent(event: KeyboardEvent) {
  if (event.key.toLowerCase() !== 'a' || !(event.metaKey || event.ctrlKey || event.altKey) || event.shiftKey) return;
  const path = event.composedPath();
  if (path.some(node => node instanceof Element && node.matches(editable))) return;
  const selection = window.getSelection();
  const anchor = selection?.anchorNode;
  const element = anchor instanceof Element ? anchor : anchor?.parentElement;
  const target = event.target instanceof Element ? event.target : null;
  const block = target?.closest(reading) || (selection?.toString() ? element?.closest(reading) : null);
  event.preventDefault();
  if (block && !block.closest('[hidden],[inert]')) {
    const range = document.createRange();
    range.selectNodeContents(block);
    selection?.removeAllRanges();
    selection?.addRange(range);
  }
}
