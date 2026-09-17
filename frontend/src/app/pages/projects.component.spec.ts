import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { ProjectsComponent } from './projects.component';
import { ApiService } from '../core/api.service';
import { AuthService } from '../core/auth.service';
import { DashboardPreferencesService } from '../core/dashboard-preferences.service';
import { InspectionService } from '../core/inspection.service';

describe('project creation validation', () => {
  it('allows either capability but not neither', async () => {
    const fixture = await createComponent(vi.fn().mockResolvedValue([]));
    const form = fixture.componentInstance.form;
    form.controls.key.setValue('capabilities');
    form.controls.name.setValue('Capabilities');
    form.controls.tasks_enabled.setValue(false);
    form.controls.notes_enabled.setValue(false);
    expect(form.invalid).toBe(true);
    form.controls.tasks_enabled.setValue(true);
    expect(form.valid).toBe(true);
    form.controls.notes_enabled.setValue(true);
    expect(form.valid).toBe(true);
  });
  it('shows validation feedback and does not submit an invalid project', async () => {
    const request = vi.fn().mockResolvedValue([]);
    const fixture = await createComponent(request);
    const form = fixture.nativeElement.querySelector('dialog form:last-child') as HTMLFormElement;
    form.dispatchEvent(new Event('submit'));
    fixture.detectChanges();
    expect(request).not.toHaveBeenCalledWith('/api/projects', expect.anything());
    expect(fixture.nativeElement.textContent).toContain('Please correct the highlighted fields');
    expect(fixture.nativeElement.textContent).toContain('Enter a valid project key.');
  });
  it('labels the new project dialog with its heading', () => {
    const heading = { setAttribute: vi.fn() }, dialog = { setAttribute: vi.fn(), querySelector: vi.fn().mockReturnValue(heading), showModal: vi.fn() };
    const component = { dialog: () => ({ nativeElement: dialog }) } as unknown as ProjectsComponent;
    ProjectsComponent.prototype.openDialog.call(component);
    expect(dialog.setAttribute).toHaveBeenCalledWith('aria-labelledby', 'new-project-heading');
    expect(heading.setAttribute).toHaveBeenCalledWith('id', 'new-project-heading');
  });
  it('submits a notes-only project and opens Notes', async () => {
    const request = vi.fn().mockImplementation((path: string, options?: { method?: string }) => options?.method === 'POST' ? Promise.resolve({ key: 'notes', tasks_enabled: false, notes_enabled: true }) : Promise.resolve([]));
    const fixture = await createComponent(request);
    const native = fixture.nativeElement as HTMLElement;
    setInput(native, 'key', 'notes'); setInput(native, 'name', 'Notes');
    const tasks = native.querySelector('[formControlName="tasks_enabled"]') as HTMLInputElement, notes = native.querySelector('[formControlName="notes_enabled"]') as HTMLInputElement;
    tasks.checked = false; tasks.dispatchEvent(new Event('change'));
    notes.checked = true; notes.dispatchEvent(new Event('change'));
    native.querySelector('dialog form:last-child')?.dispatchEvent(new Event('submit'));
    await vi.waitFor(() => expect(request).toHaveBeenCalledWith('/api/projects', { method: 'POST', body: { key: 'notes', name: 'Notes', description: '', color: '#80643d', tasks_enabled: false, notes_enabled: true } }));
    expect(TestBed.inject(Router).navigateByUrl).toHaveBeenCalledWith('/projects/notes/notes');
  });
  it('normalizes a project key before submission', async () => {
    const request = vi.fn().mockImplementation((path: string, options?: { method?: string }) => options?.method === 'POST' ? Promise.resolve({ key: 'notes', tasks_enabled: false, notes_enabled: true }) : Promise.resolve([]));
    const fixture = await createComponent(request);
    fixture.componentInstance.form.setValue({ key: ' Notes ', name: 'Notes', description: '', color: '#80643d', tasks_enabled: false, notes_enabled: true });
    await fixture.componentInstance.create();
    expect(request).toHaveBeenCalledWith('/api/projects', expect.objectContaining({ body: expect.objectContaining({ key: 'notes' }) }));
  });
  it('presents a notes-only card without task content', async () => {
    const fixture = await createComponent(vi.fn().mockResolvedValue([{ id: 1, key: 'notes', name: 'Notes', tasks_enabled: false, notes_enabled: true, todo_count: 3, done_count: 2, note_count: 1, todo_preview: [{ id: 1, title: 'Hidden task' }] }]));
    fixture.componentInstance.projects.set([{ id: 1, key: 'notes', name: 'Notes', tasks_enabled: false, notes_enabled: true, todo_count: 3, done_count: 2, note_count: 1, todo_preview: [{ id: 1, title: 'Hidden task' }] } as never]);
    fixture.detectChanges();
    const card = fixture.nativeElement.querySelector('.project-card') as HTMLElement;
    expect(card.textContent).toContain('Notes');
    expect(card.textContent).not.toContain('TODO');
    expect(card.textContent).not.toContain('DONE');
    expect(card.textContent).not.toContain('Hidden task');
    expect(normalized(card.querySelector('[aria-disabled="true"]')?.textContent)).toBe('Tasks · Off');
    expect(card.querySelector('a[href="/projects/notes/notes"]')?.textContent).toContain('Notes');
  });
  it('renders equal capability links and readable empty states', async () => {
    const project = { id: 1, key: 'both', name: 'Both', tasks_enabled: true, notes_enabled: true, todo_count: 0, done_count: 0, note_count: 0, todo_preview: [] };
    const fixture = await createComponent(vi.fn().mockResolvedValue([project]));
    fixture.componentInstance.projects.set([project] as never);
    fixture.detectChanges();
    expect(Array.from(fixture.nativeElement.querySelectorAll('.home-capabilities a') as NodeListOf<Element>).map(link => normalized(link.textContent))).toEqual(['Tasks · 0 open / 0 done', 'Notes · 0']);
  });
  it('links activity to its task or note and keeps its exact timestamp tooltip', async () => {
    const task = { id: 7, title: 'Task', priority: 'HIGH', updated_at: '2026-01-02T12:00:00Z' };
    const note = { id: 8, title: 'Note', updated_at: '2026-01-02T12:01:00Z', folder_path: null };
    const project = { id: 1, key: 'both', name: 'Both', tasks_enabled: true, notes_enabled: true, todo_count: 0, done_count: 0, note_count: 1, todo_preview: [task], recent_note: note, latest_activity: { action: 'NOTE_UPDATED', object_type: 'NOTE', object_id: note.id, object_title: note.title, actor: 'Admin', created_at: note.updated_at } };
    const fixture = await createComponent(vi.fn().mockResolvedValue([project]), { showArchived: false, showDescription: false, showTaskPreview: true, previewCount: 1, showLatestActivity: true, showRecentNote: true });
    fixture.componentInstance.projects.set([project] as never);
    fixture.detectChanges();
    const card = fixture.nativeElement.querySelector('.project-card') as HTMLElement;
    const activityLink = card.querySelector('.activity a') as HTMLAnchorElement;
    expect(activityLink.getAttribute('href')).toBe('/notes/8');
    expect((card.querySelector('.task-previews a') as HTMLAnchorElement).getAttribute('title')).toBe(task.updated_at);
  });
  it('renders readable activity, capability, and recent-note copy', async () => {
    const updatedAt = new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString();
    const taskProject = { id: 1, key: 'tasks', name: 'Tasks', tasks_enabled: true, notes_enabled: false, todo_count: 4, done_count: 0, note_count: 0, todo_preview: [], latest_activity: { action: 'CREATED', object_type: 'TASK', object_id: 7, object_title: 'trhee', actor: 'Local Administrator', created_at: updatedAt } };
    const noteProject = { id: 2, key: 'notes', name: 'Notes', tasks_enabled: false, notes_enabled: true, todo_count: 0, done_count: 0, note_count: 2, todo_preview: [], recent_note: { id: 8, title: 'one', updated_at: updatedAt, updater: 'Local Administrator', folder_path: null }, latest_activity: { action: 'NOTE_UPDATED', object_type: 'NOTE', object_id: 8, object_title: 'one', actor: 'Local Administrator', created_at: updatedAt } };
    const fixture = await createComponent(vi.fn().mockResolvedValue([taskProject, noteProject]), { showArchived: false, showDescription: false, showTaskPreview: false, previewCount: 0, showLatestActivity: true, showRecentNote: true });
    fixture.componentInstance.projects.set([taskProject, noteProject] as never);
    fixture.detectChanges();
    const [taskCard, noteCard] = Array.from(fixture.nativeElement.querySelectorAll('.project-card') as NodeListOf<HTMLElement>);
    expect(normalized(taskCard.querySelector('.activity')?.textContent)).toBe('Local Administrator created task “trhee” · 3 hours ago');
    expect(normalized(noteCard.querySelector('.activity')?.textContent)).toBe('Local Administrator updated note “one” · 3 hours ago');
    expect(normalized(taskCard.querySelector('.home-capabilities a')?.textContent)).toBe('Tasks · 4 open / 0 done');
    expect(normalized(taskCard.querySelector('.home-capabilities [aria-disabled]')?.textContent)).toBe('Notes · Off');
    expect(normalized(noteCard.querySelector('.home-capabilities [aria-disabled]')?.textContent)).toBe('Tasks · Off');
    expect(normalized(noteCard.querySelector('.home-capabilities a')?.textContent)).toBe('Notes · 2');
    expect(normalized(noteCard.querySelector('.recent-note small')?.textContent)).toBe('Edited by Local Administrator · 3 hours ago');
    expect(noteCard.querySelector('.recent-note')?.getAttribute('title')).toBe(updatedAt);
    expect(noteCard.querySelector('.activity a')?.getAttribute('title')).toBe(updatedAt);
  });
});

async function createComponent(request: ReturnType<typeof vi.fn>, preferences = { showArchived: false, showDescription: false, showTaskPreview: false, previewCount: 0, showLatestActivity: false, showRecentNote: false }) {
  await TestBed.configureTestingModule({ imports: [ProjectsComponent], providers: [provideRouter([]), { provide: ApiService, useValue: { request } }, { provide: AuthService, useValue: { user: () => undefined } }, { provide: InspectionService, useValue: { active: () => false } }, { provide: DashboardPreferencesService, useValue: { value: () => preferences } }] }).compileComponents();
  const router = TestBed.inject(Router); vi.spyOn(router, 'navigateByUrl').mockResolvedValue(true);
  const fixture = TestBed.createComponent(ProjectsComponent); fixture.detectChanges(); await fixture.whenStable(); return fixture;
}

function setInput(root: HTMLElement, control: string, value: string) { const input = root.querySelector(`[formControlName="${control}"]`) as HTMLInputElement; input.value = value; input.dispatchEvent(new Event('input')); }
function normalized(value: string | null | undefined) { return value?.replace(/\s+/g, ' ').trim(); }
