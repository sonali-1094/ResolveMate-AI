import test from 'node:test';
import assert from 'node:assert/strict';
import { acquireChatSubmit, releaseChatSubmit } from './chatSubmitGuard.js';

test('duplicate submit events start only one chat request while one is in flight', () => {
  const lock = { current: false };
  let requestCount = 0;

  const submit = () => {
    if (!acquireChatSubmit(lock)) return;
    requestCount += 1;
  };

  submit();
  submit();

  assert.equal(requestCount, 1);
  releaseChatSubmit(lock);
  submit();
  assert.equal(requestCount, 2);
});
