/**
 * A keyed async queue that serializes async tasks per key.
 * Kept local so transcript mirroring can serialize writes without depending on
 * extra platform internals.
 *
 * Matches the behaviour of the upstream implementation: a failed task
 * does not block subsequent tasks on the same key.
 */
export class KeyedAsyncQueue {
  private readonly tails = new Map<string, Promise<void>>();

  enqueue<T>(key: string, task: () => Promise<T>): Promise<T> {
    const current = (this.tails.get(key) ?? Promise.resolve())
      .catch(() => void 0)
      .then(task);
    const tail = current.then(
      () => void 0,
      () => void 0,
    );
    this.tails.set(key, tail);
    tail.finally(() => {
      if (this.tails.get(key) === tail) this.tails.delete(key);
    });
    return current;
  }
}
