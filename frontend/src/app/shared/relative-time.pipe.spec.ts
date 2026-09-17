import { RelativeTimePipe } from './relative-time.pipe';

describe('RelativeTimePipe', () => {
  it('uses exact second, minute, hour, and day boundaries', () => {
    const pipe = new RelativeTimePipe(), now = new Date('2026-01-02T12:00:00Z');
    expect(pipe.transform('2026-01-02T11:59:01Z', now)).toBe('59 seconds ago');
    expect(pipe.transform('2026-01-02T11:59:00Z', now)).toBe('1 minute ago');
    expect(pipe.transform('2026-01-02T11:01:00Z', now)).toBe('59 minutes ago');
    expect(pipe.transform('2026-01-02T11:00:00Z', now)).toBe('1 hour ago');
    expect(pipe.transform('2026-01-01T13:00:00Z', now)).toBe('23 hours ago');
    expect(pipe.transform('2026-01-01T12:00:00Z', now)).toBe('yesterday');
  });

  it('explicitly formats relative times in English', () => {
    const native = Intl.RelativeTimeFormat;
    let locale: string | string[] | undefined;
    class TrackingRelativeTimeFormat extends native {
      constructor(value: string | string[], options?: Intl.RelativeTimeFormatOptions) { locale = value; super(value, options); }
    }
    vi.stubGlobal('Intl', { ...Intl, RelativeTimeFormat: TrackingRelativeTimeFormat });
    try {
      expect(new RelativeTimePipe().transform('2026-01-02T09:00:00Z', new Date('2026-01-02T12:00:00Z'))).toBe('3 hours ago');
      expect(locale).toBe('en');
    } finally { vi.unstubAllGlobals(); }
  });
});
