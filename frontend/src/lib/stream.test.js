import { describe, expect, it } from 'vitest';

import { takeFrames } from './stream';

describe('takeFrames', () => {
  it('parses complete events and keeps a partial frame', () => {
    const first = takeFrames('event: token\ndata: {"text":"Hi"}\n\nevent: done\ndata: {"id":');
    expect(first.frames).toEqual([{ event: 'token', data: { text: 'Hi' } }]);
    const second = takeFrames(`${first.rest}"1"}\n\n`);
    expect(second.frames).toEqual([{ event: 'done', data: { id: '1' } }]);
    expect(second.rest).toBe('');
  });
});
