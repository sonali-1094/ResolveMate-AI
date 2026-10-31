export function acquireChatSubmit(lock) {
  if (lock.current) return false;
  lock.current = true;
  return true;
}

export function releaseChatSubmit(lock) {
  lock.current = false;
}
