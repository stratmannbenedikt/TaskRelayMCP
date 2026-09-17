import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { HeaderComponent } from './header.component';
import { ApiService } from '../core/api.service';
import { AuthService } from '../core/auth.service';
import { InspectionService } from '../core/inspection.service';

describe('HeaderComponent', () => {
  afterEach(() => vi.unstubAllGlobals());
  it('is open and keyboard-accessible on desktop', async () => {
    const fixture = await createHeader(true, []);
    const sidebar = fixture.nativeElement.querySelector('aside');
    expect(sidebar.getAttribute('aria-hidden')).toBe('false');
    expect(sidebar.hasAttribute('inert')).toBe(false);
  });
  it('is closed and inert on mobile', async () => {
    const fixture = await createHeader(false, []);
    const sidebar = fixture.nativeElement.querySelector('aside');
    expect(sidebar.getAttribute('aria-hidden')).toBe('true');
    expect(sidebar.hasAttribute('inert')).toBe(true);
  });
  it('reactively closes and inerts the sidebar after a desktop to mobile resize', async () => {
    let listener!: (event: MediaQueryListEvent) => void;
    const media = { matches: true, addEventListener: vi.fn((_type: string, callback: (event: MediaQueryListEvent) => void) => listener = callback), removeEventListener: vi.fn() };
    vi.stubGlobal('matchMedia', () => media);
    const request = vi.fn().mockResolvedValue([]);
    await TestBed.configureTestingModule({ imports: [HeaderComponent], providers: [provideRouter([]), { provide: ApiService, useValue: { request } }, { provide: AuthService, useValue: { user: () => undefined, logout: vi.fn() } }, { provide: InspectionService, useValue: { active: () => false } }] }).compileComponents();
    const fixture = TestBed.createComponent(HeaderComponent); fixture.detectChanges();
    listener({ matches: false } as MediaQueryListEvent); fixture.detectChanges();
    const sidebar = fixture.nativeElement.querySelector('aside');
    expect(sidebar.classList).not.toContain('open');
    expect(sidebar.getAttribute('aria-hidden')).toBe('true');
    expect(sidebar.hasAttribute('inert')).toBe(true);
    fixture.destroy();
    expect(media.removeEventListener).toHaveBeenCalledWith('change', listener);
  });
  it('renders an owner settings cog beside direct capability links', async () => {
    const fixture = await createHeader(true, [{ id: 1, key: 'both', name: 'Both', tasks_enabled: true, notes_enabled: true, role: 'OWNER' }]);
    expect(fixture.nativeElement.textContent).toContain('My Projects');
    expect([...fixture.nativeElement.querySelectorAll('.my-projects a')].map((link: HTMLAnchorElement) => link.getAttribute('href'))).toEqual(['/projects/both/settings', '/projects/both/tasks', '/projects/both/notes']);
    expect(fixture.nativeElement.querySelector('.project-settings-cog')?.getAttribute('aria-label')).toBe('Settings for Both');
    expect(fixture.nativeElement.textContent).not.toContain('Project settings');
    expect(fixture.nativeElement.querySelector('a[href="/projects/both"]')).toBeNull();
  });
  it('keeps project title text at AA contrast against the sidebar', async () => {
    const component = (await createHeader(true, [])).componentInstance;
    for (const color of ['#ffffff', '#000000', '#ff00ff']) expect(contrast(component.titleColor(color), '#fffdfa')).toBeGreaterThanOrEqual(4.5);
  });
});

async function createHeader(desktop: boolean, projects: unknown[]) {
  vi.stubGlobal('matchMedia', () => ({ matches: desktop, addEventListener: vi.fn(), removeEventListener: vi.fn() }));
  const request = vi.fn().mockResolvedValue(projects);
  await TestBed.configureTestingModule({ imports: [HeaderComponent], providers: [provideRouter([]), { provide: ApiService, useValue: { request } }, { provide: AuthService, useValue: { user: () => undefined, logout: vi.fn() } }, { provide: InspectionService, useValue: { active: () => false } }] }).compileComponents();
  const fixture = TestBed.createComponent(HeaderComponent); fixture.detectChanges(); await fixture.whenStable(); fixture.detectChanges();
  expect(request).toHaveBeenCalledWith('/api/projects?inspection=false&include_archived=false');
  return fixture;
}

function contrast(foreground: string, background: string) {
  const luminance = (color: string) => color.slice(1).match(/../g)!.map(channel => parseInt(channel, 16) / 255).map(channel => channel <= .04045 ? channel / 12.92 : ((channel + .055) / 1.055) ** 2.4).reduce((sum, channel, index) => sum + channel * [.2126, .7152, .0722][index], 0);
  const [a, b] = [luminance(foreground), luminance(background)].sort((left, right) => right - left);
  return (a + .05) / (b + .05);
}
