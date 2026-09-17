import { NotesComponent } from './notes.component';
import { FormControl, FormGroup } from '@angular/forms';
import { signal } from '@angular/core';
import { ApiError } from '../core/api.service';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter, Router } from '@angular/router';
import { BehaviorSubject } from 'rxjs';
import { AuthService } from '../core/auth.service';
import { InspectionService } from '../core/inspection.service';
import { ApiService } from '../core/api.service';

describe('NotesComponent helpers', () => {
  it('renders safe wiki links and marks unresolved links', () => {
    const component = { note: () => ({ references: [{ id: 42 }] }), notes: () => [], key: () => 'alpha' } as unknown as NotesComponent;
    const html = NotesComponent.prototype.render.call(component, '<script>x</script> [[N-42|Plan]] [[N-7]]');
    expect(html).toContain('/projects/alpha/notes/42');
    expect(html).toContain('Unresolved N-7');
    expect(html).not.toContain('<script>');
  });
  it('renders the focused editor workspace and formats Markdown at the textarea selection', async () => {
    const form = new FormGroup({ markdown: new FormControl('', { nonNullable: true }) });
    const component = { form, prefix: NotesComponent.prototype['prefix'], wrap: NotesComponent.prototype['wrap'], replace: NotesComponent.prototype['replace'] } as unknown as NotesComponent;
    const editor = document.createElement('textarea'); document.body.append(editor);
    NotesComponent.prototype.format.call(component, editor, 'bold'); editor.value = form.controls.markdown.value; await Promise.resolve();
    expect(form.controls.markdown.value).toBe('**bold text**'); expect(form.dirty).toBe(true); expect(document.activeElement).toBe(editor); expect([editor.selectionStart, editor.selectionEnd]).toEqual([2, 11]);
    editor.value = 'one\ntwo'; form.controls.markdown.setValue(editor.value); editor.setSelectionRange(0, editor.value.length);
    NotesComponent.prototype.format.call(component, editor, 'bulleted-list'); await Promise.resolve();
    expect(form.controls.markdown.value).toBe('- one\n- two');
    editor.value = 'code'; form.controls.markdown.setValue(editor.value); editor.setSelectionRange(0, 4);
    NotesComponent.prototype.format.call(component, editor, 'code'); await Promise.resolve(); expect(form.controls.markdown.value).toBe('`code`');
    editor.value = ''; form.controls.markdown.setValue(''); editor.setSelectionRange(0, 0);
    NotesComponent.prototype.format.call(component, editor, 'code'); await Promise.resolve(); expect(form.controls.markdown.value).toBe('```\ncode\n```');
    editor.value = ''; form.controls.markdown.setValue(''); editor.setSelectionRange(0, 0);
    NotesComponent.prototype.format.call(component, editor, 'table'); await Promise.resolve(); expect(form.controls.markdown.value).toBe('| Header 1 | Header 2 |\n| --- | --- |\n| Cell 1 | Cell 2 |');
    editor.value = form.controls.markdown.value; editor.setSelectionRange(editor.value.length, editor.value.length); editor.maxLength = form.controls.markdown.value.length; const before = form.controls.markdown.value;
    NotesComponent.prototype.format.call(component, editor, 'bold'); expect(form.controls.markdown.value).toBe(before); editor.remove();
  });
  it('excludes a folder and descendants as move parents', () => {
    const component = { folders: () => [{ id: 1, parent_id: null }, { id: 2, parent_id: 1 }, { id: 3, parent_id: null }], descends: NotesComponent.prototype['descends'] } as unknown as NotesComponent;
    expect(NotesComponent.prototype.parents.call(component, { id: 1, parent_id: null } as never)).toEqual([{ id: 3, parent_id: null }]);
  });
  it('moves folders only to valid new parents and leaves same-parent drops alone', async () => {
    const request = vi.fn().mockResolvedValue({}), event = { preventDefault: vi.fn(), stopPropagation: vi.fn() } as unknown as DragEvent;
    const component = { writable: () => true, folders: () => [{ id: 1, parent_id: null }, { id: 2, parent_id: 1 }, { id: 3, parent_id: null }], notes: () => [], dragging: () => ({ kind: 'folder' as const, id: 1 }), parents: NotesComponent.prototype.parents, descends: NotesComponent.prototype['descends'], canDrop: NotesComponent.prototype.canDrop, endDrag: vi.fn(), moveFolder: NotesComponent.prototype.moveFolder, run: async (action: () => Promise<unknown>) => action(), api: { request } } as unknown as NotesComponent;
    await NotesComponent.prototype.drop.call(component, event, 3);
    expect(request).toHaveBeenCalledWith('/api/note-folders/1', { method: 'PATCH', body: { parent_id: 3 } });
    expect(NotesComponent.prototype.canDrop.call(component, 1)).toBe(false);
    expect(NotesComponent.prototype.canDrop.call(component, 2)).toBe(false);
    expect(NotesComponent.prototype.canDrop.call(component, null)).toBe(false);
    const sameParent = { ...component, dragging: () => ({ kind: 'folder' as const, id: 2 }) } as unknown as NotesComponent;
    expect(NotesComponent.prototype.canDrop.call(sameParent, 1)).toBe(false);
    expect(NotesComponent.prototype.canDrop.call(sameParent, null)).toBe(true);
  });
  it('moves notes with their current content and expected version', async () => {
    const request = vi.fn().mockResolvedValue({}), event = { preventDefault: vi.fn(), stopPropagation: vi.fn() } as unknown as DragEvent;
    const component = { writable: () => true, folders: () => [], notes: () => [{ id: 4, title: 'Title', markdown: 'text', folder_id: null, version: 2, archived_at: null }], dragging: () => ({ kind: 'note' as const, id: 4 }), canDrop: NotesComponent.prototype.canDrop, endDrag: vi.fn(), run: async (action: () => Promise<unknown>) => action(), api: { request } } as unknown as NotesComponent;
    await NotesComponent.prototype.drop.call(component, event, 7);
    expect(request).toHaveBeenCalledWith('/api/notes/4', { method: 'PATCH', body: { title: 'Title', markdown: 'text', folder_id: 7, expected_version: 2 } });
  });
  it('sends expected_version and exposes a conflict instead of overwriting', async () => {
    const request = vi.fn().mockRejectedValue(new ApiError('changed', 409));
    const conflict = vi.fn();
    const component = { api: { request }, note: () => ({ id: 4, version: 2 }), draft: () => false, writable: () => true, editing: { set: vi.fn() }, form: new FormGroup({ title: new FormControl('Title', { nonNullable: true }), markdown: new FormControl('text', { nonNullable: true }), folder_id: new FormControl('', { nonNullable: true }) }), conflict: { set: conflict }, error: { set: vi.fn() }, loadNote: vi.fn() } as unknown as NotesComponent;
    await NotesComponent.prototype.save.call(component);
    expect(request.mock.calls[0][1].body.expected_version).toBe(2);
    expect(conflict).toHaveBeenCalledWith(true);
  });
  it('redirects a tasks-only project before loading notes or folders', async () => {
    const request = vi.fn().mockResolvedValue([{ key: 'tasks', tasks_enabled: true, notes_enabled: false }]);
    const navigateByUrl = vi.fn().mockResolvedValue(true);
    const component = { api: { request }, router: { navigateByUrl }, key: () => 'tasks', noteId: () => undefined, inspection: { active: () => false }, editing: { set: vi.fn() }, note: { set: vi.fn() }, revisions: { set: vi.fn() } } as unknown as NotesComponent;
    await NotesComponent.prototype.load.call(component);
    expect(navigateByUrl).toHaveBeenCalledWith('/projects/tasks/tasks', { replaceUrl: true });
    expect(request).not.toHaveBeenCalledWith(expect.stringContaining('note-'));
    expect(request).not.toHaveBeenCalledWith(expect.stringContaining('/notes'));
  });
  it('renders the local tree without page navigation and nests notes under folders', async () => {
    const request = vi.fn().mockImplementation((path: string) => Promise.resolve(path.startsWith('/api/projects?') ? [{ key: 'notes', name: 'Notes project', role: 'OWNER', archived: false, tasks_enabled: false, notes_enabled: true }] : path.includes('note-folders') ? [{ id: 1, name: 'Root folder', parent_id: null }, { id: 2, name: 'Nested folder', parent_id: 1 }] : path.includes('/notes?') ? [{ id: 3, title: 'Nested note', folder_id: 2, archived_at: null }] : []));
    await TestBed.configureTestingModule({ imports: [NotesComponent], providers: [provideRouter([]), { provide: ApiService, useValue: { request } }, { provide: AuthService, useValue: { user: () => undefined } }, { provide: InspectionService, useValue: { active: () => false } }] }).compileComponents();
    const router = TestBed.inject(Router); vi.spyOn(router, 'navigateByUrl').mockResolvedValue(true);
    const fixture = TestBed.createComponent(NotesComponent); fixture.detectChanges(); await fixture.whenStable(); fixture.componentInstance.project.set({ key: 'notes', name: 'Notes project', role: 'OWNER', archived: false, tasks_enabled: false, notes_enabled: true } as never); fixture.componentInstance.folders.set([{ id: 1, name: 'Root folder', parent_id: null }, { id: 2, name: 'Nested folder', parent_id: 1 }] as never); fixture.componentInstance.notes.set([{ id: 3, title: 'Nested note', folder_id: 2, archived_at: null }] as never); fixture.detectChanges();
    const page = fixture.nativeElement as HTMLElement;
    expect(page.querySelector('main > nav')).toBeNull();
    expect(page.querySelector('.folders input')).not.toBeNull();
    const rootToggle = page.querySelector<HTMLButtonElement>('[aria-label="Collapse Notes project"]')!;
    expect(rootToggle.getAttribute('aria-expanded')).toBe('true');
    expect(rootToggle.classList).toContain('tree-control');
    expect(page.querySelector('[aria-label="Add to project root"]')).not.toBeNull();
    expect(page.querySelector('[aria-label="Add to Root folder"]')).not.toBeNull();
    expect(page.querySelector('[aria-label="Add to Nested folder"]')).not.toBeNull();
    const folder = page.querySelector('.folder-tree')!, toggle = folder.querySelector<HTMLButtonElement>('[aria-label="Collapse Root folder"]')!;
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    expect(folder.querySelector('.tree-folder-marker')?.getAttribute('aria-hidden')).toBe('true');
    expect(page.querySelector('.project-note-tree > .tree-children > .folder-tree > .tree-children > .folder-tree')).not.toBeNull();
    const folderHandle = folder.querySelector<HTMLElement>('[data-drag-folder="1"]')!;
    expect(folderHandle.getAttribute('draggable')).toBe('true');
    expect(folderHandle.getAttribute('title')).toBe('Drag Root folder');
    expect(folderHandle.getAttribute('aria-hidden')).toBe('true');
    expect(folderHandle.hasAttribute('tabindex')).toBe(false);
    expect(folderHandle.hasAttribute('role')).toBe(false);
    expect(folder.querySelector('.tree-name')?.getAttribute('draggable')).toBeNull();
    expect(folder.querySelector('.tree-row-actions')!.textContent).toBe('+…');
    toggle.click(); fixture.detectChanges();
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expect(page.querySelector('[aria-label="Collapse Nested folder"]')).toBeNull();
    expect(page.querySelector('.note-tree')).toBeNull();
    toggle.click(); fixture.detectChanges();
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    const add = folder.querySelector<HTMLButtonElement>('[aria-label="Add to Root folder"]')!, manage = folder.querySelector<HTMLButtonElement>('[aria-label="Manage Root folder"]')!;
    add.click(); fixture.detectChanges();
    expect(add.getAttribute('aria-expanded')).toBe('true');
    expect(folder.querySelector('.tree-action-panel')?.previousElementSibling).toBe(folder.querySelector('.tree-row'));
    manage.click(); fixture.detectChanges();
    expect(add.getAttribute('aria-expanded')).toBe('false');
    expect(manage.getAttribute('aria-expanded')).toBe('true');
    expect(folder.querySelector('.tree-action-panel')?.textContent).toContain('Rename');
    expect(Array.from(folder.querySelectorAll('.tree-action-panel > *')).map(item => item.textContent?.trim())).toEqual(['Rename', 'MoveRoot', 'Delete']);
    expect(folder.querySelector<HTMLSelectElement>('.tree-action-panel label select')).not.toBeNull();
    const noteLinks = page.querySelectorAll('.note-tree');
    expect(noteLinks).toHaveLength(1);
    expect(noteLinks[0].previousElementSibling?.classList).toContain('tree-note-marker');
    expect(noteLinks[0].previousElementSibling?.getAttribute('aria-hidden')).toBe('true');
    expect(noteLinks[0].getAttribute('href')).toMatch(/\/projects\/.*\/notes\/3$/);
    expect(noteLinks[0].getAttribute('draggable')).toBeNull();
    const noteHandle = page.querySelector<HTMLElement>('[data-drag-note="3"]')!;
    expect(noteHandle.getAttribute('draggable')).toBe('true');
    expect(noteHandle.getAttribute('title')).toBe('Drag Nested note');
    expect(noteHandle.getAttribute('aria-hidden')).toBe('true');
    expect(noteHandle.hasAttribute('tabindex')).toBe(false);
    expect(noteHandle.hasAttribute('role')).toBe(false);
    rootToggle.click(); fixture.detectChanges();
    expect(rootToggle.getAttribute('aria-expanded')).toBe('false');
    expect(page.querySelector('.folder-tree')).toBeNull();
    fixture.componentInstance.search.setValue('Nested'); await fixture.whenStable(); fixture.detectChanges();
    expect(rootToggle.getAttribute('aria-expanded')).toBe('true');
    expect(page.querySelector('[aria-label="Collapse Nested folder"]')).not.toBeNull();
    expect(page.querySelector('.note-tree')?.textContent).toContain('Nested note');
    fixture.componentInstance.search.setValue(''); await fixture.whenStable(); fixture.detectChanges();
    expect(rootToggle.getAttribute('aria-expanded')).toBe('false');
    expect(page.querySelector('.folder-tree')).toBeNull();
  });
  it('renders a directly opened existing note read-only until Edit is pressed', async () => {
    const params = new BehaviorSubject(convertToParamMap({ key: 'notes', noteId: '4' }));
    const note = { id: 4, title: 'Read only', markdown: '# Safe', folder_id: 2, version: 1, updated_at: '2026-01-01T00:00:00Z', updater: '', archived_at: null, backlinks: [], references: [] };
    const request = vi.fn((path: string) => Promise.resolve(path.startsWith('/api/projects?') ? [{ key: 'notes', role: 'MEMBER', archived: false, tasks_enabled: false, notes_enabled: true }] : path.startsWith('/api/notes/4/revisions') ? [] : path.includes('/note-folders') ? [{ id: 1, name: 'Root folder', parent_id: null }, { id: 2, name: 'Nested folder', parent_id: 1 }] : path.includes('/projects/notes/notes') ? [note] : note));
    await TestBed.configureTestingModule({ imports: [NotesComponent], providers: [provideRouter([]), { provide: ActivatedRoute, useValue: { paramMap: params, get snapshot() { return { paramMap: params.value, data: {} }; } } }, { provide: ApiService, useValue: { request } }, { provide: AuthService, useValue: { user: () => undefined } }, { provide: InspectionService, useValue: { active: () => false } }] }).compileComponents();
    const fixture = TestBed.createComponent(NotesComponent); fixture.detectChanges(); await fixture.componentInstance.load(); fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).querySelector('textarea')).toBeNull();
    expect(fixture.componentInstance.editing()).toBe(false);
    expect(Array.from((fixture.nativeElement as HTMLElement).querySelectorAll('button')).some(button => button.textContent?.includes('Edit'))).toBe(true);
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Read only');
    const noteLinks = (fixture.nativeElement as HTMLElement).querySelectorAll('.note-tree');
    expect(noteLinks).toHaveLength(1);
    expect(noteLinks[0].getAttribute('href')).toMatch(/\/projects\/notes\/notes\/4$/);
    expect(noteLinks[0].getAttribute('aria-current')).toBe('page');
    expect(noteLinks[0].closest('.note-tree-row')?.classList).toContain('selected');
    expect(noteLinks[0].previousElementSibling?.classList).toContain('tree-note-marker');
    expect((fixture.nativeElement as HTMLElement).querySelector('article.preview h3')?.textContent).toBe('Read only');
    expect((fixture.nativeElement as HTMLElement).querySelector('time')?.getAttribute('title')).toBe(note.updated_at);
    const reader = (fixture.nativeElement as HTMLElement).querySelector('.note-reader')!;
    expect(reader.querySelector('h4')?.textContent).not.toBe('Preview');
    expect(reader.querySelector('.note-reader-actions')!.compareDocumentPosition(reader.querySelector('.note-reader-meta')!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(reader.querySelector('.note-reader-meta')!.compareDocumentPosition(reader.querySelector('.note-reader-body')!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    fixture.componentInstance.edit(); fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).querySelector('textarea')).not.toBeNull();
    expect((fixture.nativeElement as HTMLElement).querySelector('.notes-layout.is-editing .folders')).not.toBeNull();
    expect((fixture.nativeElement as HTMLElement).querySelector('.note-edit-workspace')).not.toBeNull();
    expect((fixture.nativeElement as HTMLElement).querySelector('[role="toolbar"][aria-label="Markdown formatting"]')?.querySelectorAll('button')).toHaveLength(9);
    expect((fixture.nativeElement as HTMLElement).querySelector('[role="toolbar"]')!.compareDocumentPosition((fixture.nativeElement as HTMLElement).querySelector('textarea')!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect((fixture.nativeElement as HTMLElement).querySelector('select[formcontrolname="folder_id"]')).not.toBeNull();
    expect((fixture.nativeElement as HTMLElement).querySelector('.preview h3')?.textContent).toBe('Preview');
  });
  it('opens a captured global edit intent after loading and consumes it', async () => {
    const { fixture } = await createNoteDetail(true);
    expect(fixture.componentInstance.canEdit()).toBe(true);
    expect(fixture.componentInstance.editing()).toBe(true);
    fixture.componentInstance.editing.set(false); await fixture.componentInstance.load(); fixture.detectChanges();
    expect(fixture.componentInstance.editing()).toBe(false);
  });
  it('keeps a captured edit intent read-only when editing is denied', async () => {
    const { fixture } = await createNoteDetail(true, true);
    expect(fixture.componentInstance.editing()).toBe(false);
  });
  it('consumes edit intent before a failed load so retry remains read-only', async () => {
    const editing = signal(false), note = signal<{ id: number } | undefined>(undefined), component = { noteEdit: 4, editing, note, revisions: signal([]), project: signal(undefined), api: { request: vi.fn().mockRejectedValueOnce(new Error('failed')).mockResolvedValueOnce([{ key: 'notes', notes_enabled: true }]) }, inspection: { active: () => false }, key: () => 'notes', noteId: () => 4, loadFolders: vi.fn(), loadNotes: vi.fn(), loadNote: async () => note.set({ id: 4 }), canEdit: () => true, draft: () => false, error: { set: vi.fn() } } as unknown as NotesComponent;
    await NotesComponent.prototype.load.call(component);
    expect((component as unknown as { noteEdit?: number }).noteEdit).toBeUndefined();
    await NotesComponent.prototype.load.call(component);
    expect(editing()).toBe(false);
  });
  it('does not edit when the captured target differs from the loaded route note', async () => {
    const editing = signal(false), note = signal<{ id: number } | undefined>(undefined), component = { noteEdit: 4, editing, note, revisions: signal([]), project: signal(undefined), api: { request: vi.fn().mockResolvedValue([{ key: 'notes', notes_enabled: true }]) }, inspection: { active: () => false }, key: () => 'notes', noteId: () => 5, loadFolders: vi.fn(), loadNotes: vi.fn(), loadNote: async () => note.set({ id: 5 }), canEdit: () => true, draft: () => false, error: { set: vi.fn() } } as unknown as NotesComponent;
    await NotesComponent.prototype.load.call(component);
    expect(editing()).toBe(false);
  });
  it('reloads pristine editors on inspection activation and preserves dirty editors when declined', async () => {
    const editing = signal(true), pristine = new FormGroup({ title: new FormControl('Saved', { nonNullable: true }) }), load = vi.fn(), inspection = { toggle: vi.fn() };
    await NotesComponent.prototype['inspectionChanged'].call({ editing, form: pristine, inspection, load, canDeactivate: NotesComponent.prototype.canDeactivate }, true);
    expect(editing()).toBe(false); expect(load).toHaveBeenCalledTimes(1);
    const dirtyEditing = signal(true), dirty = new FormGroup({ title: new FormControl('Draft', { nonNullable: true }) }), dirtyLoad = vi.fn(), dirtyInspection = { toggle: vi.fn() };
    dirty.controls.title.setValue('Unsaved'); dirty.markAsDirty(); const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    await NotesComponent.prototype['inspectionChanged'].call({ editing: dirtyEditing, form: dirty, inspection: dirtyInspection, load: dirtyLoad, canDeactivate: NotesComponent.prototype.canDeactivate }, true);
    expect(dirtyEditing()).toBe(true); expect(dirty.controls.title.value).toBe('Unsaved'); expect(dirtyInspection.toggle).toHaveBeenCalledWith(false); expect(dirtyLoad).not.toHaveBeenCalled(); confirm.mockRestore();
  });
  it('enters edit mode only after Edit and keeps archived notes read-only', () => {
    const editing = { set: vi.fn() };
    NotesComponent.prototype.edit.call({ canEdit: () => true, editing } as unknown as NotesComponent);
    expect(editing.set).toHaveBeenCalledWith(true);
    expect(NotesComponent.prototype.canEdit.call({ writable: () => true, note: () => ({ archived_at: 'now' }) } as unknown as NotesComponent)).toBe(false);
    expect(NotesComponent.prototype.canEdit.call({ writable: () => false, note: () => ({ archived_at: null }) } as unknown as NotesComponent)).toBe(false);
  });
  it('confirms only dirty edit or draft navigation', () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true);
    const component = { editing: () => true, form: { dirty: true } } as unknown as NotesComponent;
    expect(NotesComponent.prototype.canDeactivate.call(component)).toBe(false);
    expect(NotesComponent.prototype.canDeactivate.call(component)).toBe(true);
    expect(NotesComponent.prototype.canDeactivate.call({ editing: () => false, form: { dirty: true } } as unknown as NotesComponent)).toBe(true);
    expect(confirm).toHaveBeenCalledTimes(2);
  });
  it('does not POST when opening or cancelling a new local draft', async () => {
    const navigate = vi.fn().mockResolvedValue(true), request = vi.fn();
    await NotesComponent.prototype.newNote.call({ writable: () => true, router: { navigate }, key: () => 'notes' } as unknown as NotesComponent);
    expect(navigate).toHaveBeenCalledWith(['/projects', 'notes', 'notes', 'new'], undefined);
    expect(request).not.toHaveBeenCalled();
  });
  it('creates a child folder at its selected parent and starts drafts there', async () => {
    const request = vi.fn().mockResolvedValue({}), run = vi.fn(async (action: () => Promise<unknown>) => action()), navigate = vi.fn().mockResolvedValue(true);
    vi.spyOn(window, 'prompt').mockReturnValue(' Child ');
    await NotesComponent.prototype.createFolder.call({ writable: () => true, run, api: { request }, key: () => 'notes' } as unknown as NotesComponent, 7);
    expect(request).toHaveBeenCalledWith('/api/projects/notes/note-folders', { method: 'POST', body: { name: 'Child', parent_id: 7 } });
    await NotesComponent.prototype.newNote.call({ writable: () => true, router: { navigate }, key: () => 'notes' } as unknown as NotesComponent, 7);
    expect(navigate).toHaveBeenCalledWith(['/projects', 'notes', 'notes', 'new'], { queryParams: { folder_id: 7 } });
  });
  it('POSTs a draft once then navigates to its stable read route', async () => {
    const request = vi.fn().mockResolvedValue({ id: 9 }), navigate = vi.fn().mockResolvedValue(true), pristine = vi.fn();
    const component = { writable: () => true, draft: () => true, api: { request }, router: { navigate }, key: () => 'notes', form: { invalid: false, getRawValue: () => ({ title: 'Draft', markdown: 'text', folder_id: '' }), markAsPristine: pristine }, conflict: { set: vi.fn() }, error: { set: vi.fn() } } as unknown as NotesComponent;
    await NotesComponent.prototype.save.call(component);
    expect(request).toHaveBeenCalledWith('/api/projects/notes/notes', { method: 'POST', body: { title: 'Draft', markdown: 'text', folder_id: null } });
    expect(navigate).toHaveBeenCalledWith(['/projects', 'notes', 'notes', 9]);
  });
  it('returns to read mode after saving and restores with the current version', async () => {
    const editing = { set: vi.fn() }, request = vi.fn().mockResolvedValue({}), loadNote = vi.fn();
    const component = { writable: () => true, draft: () => false, note: () => ({ id: 4, version: 2 }), api: { request }, editing, form: { invalid: false, getRawValue: () => ({ title: 'Title', markdown: '', folder_id: '' }) }, conflict: { set: vi.fn() }, error: { set: vi.fn() }, loadNote } as unknown as NotesComponent;
    await NotesComponent.prototype.save.call(component);
    expect(editing.set).toHaveBeenCalledWith(false);
    expect(loadNote).toHaveBeenCalled();
    const restore = { request: vi.fn().mockResolvedValue({}) }, run = vi.fn(async (action: () => Promise<unknown>) => action());
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    await NotesComponent.prototype.restore.call({ note: () => ({ id: 4, version: 3 }), canManage: () => true, api: restore, run } as unknown as NotesComponent, 2);
    expect(restore.request).toHaveBeenCalledWith('/api/notes/4/revisions/2/restore', { method: 'POST', body: { expected_version: 3 } });
  });
});

async function createNoteDetail(noteEdit: boolean, inspection = false) {
  const params = new BehaviorSubject(convertToParamMap({ key: 'notes', noteId: '4' }));
  const note = { id: 4, title: 'Read only', markdown: '# Safe', folder_id: null, version: 1, updated_at: '2026-01-01T00:00:00Z', updater: '', archived_at: null, backlinks: [], references: [] };
  const request = vi.fn((path: string) => Promise.resolve(path.startsWith('/api/projects?') ? [{ key: 'notes', role: 'MEMBER', archived: false, tasks_enabled: false, notes_enabled: true }] : path.startsWith('/api/notes/4/revisions') ? [] : path.includes('note-folders') ? [] : path.includes('/projects/notes/notes') ? [note] : note));
  await TestBed.configureTestingModule({ imports: [NotesComponent], providers: [provideRouter([]), { provide: ActivatedRoute, useValue: { paramMap: params, get snapshot() { return { paramMap: params.value, data: {} }; } } }, { provide: ApiService, useValue: { request } }, { provide: AuthService, useValue: { user: () => undefined } }, { provide: InspectionService, useValue: { active: () => inspection } }] }).compileComponents();
  const fixture = TestBed.createComponent(NotesComponent); fixture.detectChanges(); await fixture.whenStable(); fixture.detectChanges();
  if (noteEdit) { (fixture.componentInstance as unknown as { noteEdit: number }).noteEdit = 4; await fixture.componentInstance.load(); fixture.detectChanges(); }
  return { fixture };
}
