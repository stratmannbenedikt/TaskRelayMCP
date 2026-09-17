import { TestBed } from '@angular/core/testing';
import { ActivationEnd, provideRouter, Router } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { noteUnsavedGuard, readyGuard, routes, taskUnsavedGuard } from './app.routes';
import { AuthService } from './core/auth.service';
import { ApiService } from './core/api.service';
import { InspectionService } from './core/inspection.service';
import { NotesComponent } from './pages/notes.component';
import { ProjectComponent } from './pages/project.component';
import { ProjectLandingComponent } from './pages/project-landing.component';
import { ProjectSettingsComponent } from './pages/project-settings.component';

describe('readyGuard', () => {
  it('routes a temporary-password user to password change', () => {
    const createUrlTree = vi.fn();
    TestBed.configureTestingModule({ providers: [{ provide: Router, useValue: { createUrlTree } }, { provide: AuthService, useValue: { user: () => ({ must_change_password: true }) } }] });
    TestBed.runInInjectionContext(() => readyGuard({} as never, { url: '/projects/notes/notes' } as never));
    expect(createUrlTree).toHaveBeenCalledWith(['/password-change'], { queryParams: { returnUrl: '/projects/notes/notes' } });
  });
  it('waits for session loading before allowing a deep link', async () => {
    let user: { must_change_password: boolean } | null | undefined;
    const load = vi.fn(async () => { user = { must_change_password: false }; });
    TestBed.configureTestingModule({ providers: [{ provide: Router, useValue: { createUrlTree: vi.fn() } }, { provide: AuthService, useValue: { user: () => user, load } }] });
    await expect(TestBed.runInInjectionContext(() => readyGuard({} as never, { url: '/projects/notes/notes' } as never))).resolves.toBe(true);
    expect(load).toHaveBeenCalledOnce();
  });
  it('routes to login when session loading resolves unauthenticated', async () => {
    let user: { must_change_password: boolean } | null | undefined;
    const createUrlTree = vi.fn();
    const load = vi.fn(async () => { user = null; });
    TestBed.configureTestingModule({ providers: [{ provide: Router, useValue: { createUrlTree } }, { provide: AuthService, useValue: { user: () => user, load } }] });
    await TestBed.runInInjectionContext(() => readyGuard({} as never, { url: '/projects/notes/notes' } as never));
    expect(createUrlTree).toHaveBeenCalledWith(['/login'], { queryParams: { returnUrl: '/projects/notes/notes' } });
  });
  it('routes to password change when session loading resolves a temporary-password user', async () => {
    let user: { must_change_password: boolean } | null | undefined;
    const createUrlTree = vi.fn();
    const load = vi.fn(async () => { user = { must_change_password: true }; });
    TestBed.configureTestingModule({ providers: [{ provide: Router, useValue: { createUrlTree } }, { provide: AuthService, useValue: { user: () => user, load } }] });
    await TestBed.runInInjectionContext(() => readyGuard({} as never, { url: '/projects/notes/notes' } as never));
    expect(createUrlTree).toHaveBeenCalledWith(['/password-change'], { queryParams: { returnUrl: '/projects/notes/notes' } });
  });
  it('sends an unauthenticated deep link to login with its return URL', () => {
    const createUrlTree = vi.fn();
    TestBed.configureTestingModule({ providers: [{ provide: Router, useValue: { createUrlTree } }, { provide: AuthService, useValue: { user: () => null } }] });
    TestBed.runInInjectionContext(() => readyGuard({} as never, { url: '/projects/notes/notes' } as never));
    expect(createUrlTree).toHaveBeenCalledWith(['/login'], { queryParams: { returnUrl: '/projects/notes/notes' } });
  });
});

describe('project route recognition', () => {
  let harness: RouterTestingHarness;
  const activations: unknown[] = [];

  beforeEach(async () => {
    const projects = [{ key: 'notes', name: 'Notes', tasks_enabled: false, notes_enabled: true, archived: false, role: 'MEMBER' }, { key: 'x', name: 'X', tasks_enabled: true, notes_enabled: false, archived: false, role: 'MEMBER' }];
    const request = vi.fn(async (path: string) => {
      if (path.startsWith('/api/projects?')) return projects;
      if (path.includes('/note-folders') || path.includes('/projects/notes/notes') || path.includes('/api/tasks') || path === '/api/directory') return [];
      if (path.startsWith('/api/notes/42/revisions')) return [];
      if (path.startsWith('/api/notes/42')) return { id: 42, title: 'Note', markdown: '', folder_id: null, version: 1, updated_at: '', updater: '', archived_at: null, backlinks: [], references: [] };
      return [];
    });
    await TestBed.configureTestingModule({ providers: [provideRouter(routes), { provide: AuthService, useValue: { user: () => ({ must_change_password: false, is_admin: false }) } }, { provide: ApiService, useValue: { request } }, { provide: InspectionService, useValue: { active: () => false } }] }).compileComponents();
    TestBed.inject(Router).events.subscribe(event => { if (event instanceof ActivationEnd && event.snapshot.component) activations.push(event.snapshot.component); });
    harness = await RouterTestingHarness.create();
  });

  it('activates each specific project route before the compatibility landing route', async () => {
    const landing = routes.find(route => route.path === 'projects/:key')!;
    const index = (path: string) => routes.findIndex(route => route.path === path);
    expect(landing.pathMatch).toBe('full');
    expect(index('projects/:key/tasks/:taskId')).toBeLessThan(index('projects/:key/tasks'));
    expect(index('projects/:key/tasks')).toBeLessThan(index('projects/:key'));
    expect(index('projects/:key/notes/new')).toBeLessThan(index('projects/:key/notes/:noteId'));
    expect(index('projects/:key/notes/:noteId')).toBeLessThan(index('projects/:key/notes'));
    expect(index('projects/:key/notes')).toBeLessThan(index('projects/:key'));
    expect(index('projects/:key/settings')).toBeLessThan(index('projects/:key'));
    activations.length = 0;
    await harness.navigateByUrl('/projects/notes/notes', NotesComponent);
    expect(activations).toEqual([NotesComponent]);
    activations.length = 0;
    const note = await harness.navigateByUrl('/projects/notes/notes/42', NotesComponent);
    expect(note.noteId()).toBe(42);
    expect(activations).toEqual([NotesComponent]);
    activations.length = 0;
    await harness.navigateByUrl('/projects/x/tasks', ProjectComponent);
    expect(activations).toEqual([ProjectComponent]);
    activations.length = 0;
    await harness.navigateByUrl('/projects/x/tasks/7', ProjectComponent);
    expect(activations).toEqual([ProjectComponent]);
    activations.length = 0;
    await harness.navigateByUrl('/projects/x/settings', ProjectSettingsComponent);
    expect(activations).toEqual([ProjectSettingsComponent]);
    activations.length = 0;
    await harness.navigateByUrl('/projects/x', ProjectLandingComponent);
    expect(activations).toEqual([ProjectLandingComponent]);
  });
  it('uses the note component dirty-deactivation contract', () => {
    expect(noteUnsavedGuard({ canDeactivate: () => false } as NotesComponent, {} as never, {} as never, {} as never)).toBe(false);
    expect(taskUnsavedGuard({ canDeactivate: () => false } as ProjectComponent, {} as never, {} as never, {} as never)).toBe(false);
    expect(routes.filter(route => route.component === ProjectComponent).every(route => route.canDeactivate?.includes(taskUnsavedGuard))).toBe(true);
  });
});

describe('global route aliases', () => {
  it('keeps Home primary while retaining projects as a compatibility redirect', () => {
    expect(routes.find(route => route.path === 'home')?.component).toBeDefined();
    expect(routes.find(route => route.path === 'projects')).toMatchObject({ redirectTo: 'home', pathMatch: 'full' });
    expect(routes.find(route => route.path === 'notes/:noteId')?.component).toBeDefined();
  });
});
