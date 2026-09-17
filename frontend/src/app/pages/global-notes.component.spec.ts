import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter, RouterLink } from '@angular/router';
import { By } from '@angular/platform-browser';
import { BehaviorSubject } from 'rxjs';
import { ApiService } from '../core/api.service';
import { InspectionService } from '../core/inspection.service';
import { MarkdownService } from '../core/markdown.service';
import { GlobalNotesComponent } from './global-notes.component';

describe('GlobalNotesComponent', () => {
  it('clears a reused route preview and stale error before showing a missing-note error', async () => {
    const params = new BehaviorSubject(convertToParamMap({ noteId: '1' }));
    let rejectMissing!: (reason: Error) => void;
    const request = vi.fn((path: string) => path.startsWith('/api/projects?') ? Promise.resolve([]) : path.includes('/api/notes/1?') ? Promise.resolve(note(1)) : new Promise((_, reject) => rejectMissing = reject));
    await TestBed.configureTestingModule({ imports: [GlobalNotesComponent], providers: [provideRouter([]), { provide: ActivatedRoute, useValue: { paramMap: params, get snapshot() { return { paramMap: params.value }; } } }, { provide: ApiService, useValue: { request } }, { provide: InspectionService, useValue: { active: () => false } }, { provide: MarkdownService, useValue: { render: () => '' } }] }).compileComponents();
    const fixture = TestBed.createComponent(GlobalNotesComponent); fixture.detectChanges(); await fixture.whenStable();
    const component = fixture.componentInstance;
    component.error.set('stale error');
    params.next(convertToParamMap({ noteId: '2' }));
    expect(component.note()).toBeUndefined();
    expect(component.error()).toBe('');
    rejectMissing(new Error('Note not found'));
    await fixture.whenStable();
    expect(component.note()).toBeUndefined();
    expect(component.error()).toBe('Note not found');
  });
  it('filters loaded notes by title and markdown without another request', async () => {
    const { fixture, request } = await createGlobal();
    const page = fixture.nativeElement as HTMLElement;
    expect(page.querySelectorAll('.note-tree')).toHaveLength(2);
    page.querySelector<HTMLButtonElement>('[aria-label="Collapse Folder"]')!.click(); fixture.detectChanges();
    page.querySelector<HTMLButtonElement>('[aria-label="Collapse Project"]')!.click(); fixture.detectChanges();
    const calls = request.mock.calls.length;
    fixture.componentInstance.search.setValue('needle'); fixture.detectChanges();
    expect(page.querySelector('[aria-label="Collapse Project"]')?.getAttribute('aria-expanded')).toBe('true');
    expect(page.querySelector('[aria-label="Collapse Folder"]')?.getAttribute('aria-expanded')).toBe('true');
    expect(Array.from(page.querySelectorAll('.note-tree')).map(link => link.textContent?.trim())).toEqual(['Second']);
    expect(request).toHaveBeenCalledTimes(calls);
    fixture.componentInstance.search.setValue(''); fixture.detectChanges();
    expect(page.querySelector('[aria-label="Expand Project"]')?.getAttribute('aria-expanded')).toBe('false');
    page.querySelector<HTMLButtonElement>('[aria-label="Expand Project"]')!.click(); fixture.detectChanges();
    expect(page.querySelector('[aria-label="Expand Folder"]')?.getAttribute('aria-expanded')).toBe('false');
  });
  it('uses explicit collapse controls and marks the selected note current', async () => {
    const { fixture } = await createGlobal('2');
    const page = fixture.nativeElement as HTMLElement;
    const projectToggle = page.querySelector<HTMLButtonElement>('[aria-label="Collapse Project"]')!;
    expect(projectToggle.getAttribute('aria-expanded')).toBe('true');
    projectToggle.click(); fixture.detectChanges();
    expect(page.querySelector('.folder-tree')).toBeNull();
    projectToggle.click(); fixture.detectChanges();
    const folderToggle = page.querySelector<HTMLButtonElement>('[aria-label="Collapse Folder"]')!;
    folderToggle.click(); fixture.detectChanges();
    expect(page.querySelector('.folder-tree .note-tree')).toBeNull();
    folderToggle.click(); fixture.detectChanges();
    expect(page.querySelector('.note-tree[aria-current="page"]')?.textContent).toContain('Second');
    expect(page.querySelector('.note-tree[aria-current="page"]')?.closest('.note-tree-row')?.classList).toContain('selected');
    expect(page.querySelector('.tree-folder-marker')?.getAttribute('aria-hidden')).toBe('true');
    expect(page.querySelector('.tree-note-marker')?.getAttribute('aria-hidden')).toBe('true');
    expect(page.querySelector('.project-note-tree > .tree-children > .folder-tree > .tree-children > .folder-tree')).not.toBeNull();
  });
  it('discloses the 200-note client-side search limit only when the response reaches it', async () => {
    const { fixture } = await createGlobal(undefined, 200);
    const page = fixture.nativeElement as HTMLElement;
    expect(page.querySelector('.tree-limit-notice')?.textContent).toContain('Only 200 notes are loaded');
    const tree = fixture.componentInstance.trees()[0];
    fixture.componentInstance.trees.set([{ ...tree, notes: tree.notes.slice(0, 199), truncated: false }]); fixture.detectChanges();
    expect(page.querySelector('.tree-limit-notice')).toBeNull();
  });
  it('uses the same reader metadata-before-body structure as project Notes', async () => {
    const { fixture } = await createGlobal('2'), reader = (fixture.nativeElement as HTMLElement).querySelector('.note-reader')!;
    expect(reader.querySelector('.note-reader-header')).not.toBeNull();
    expect(reader.querySelector('.note-reader-actions')!.compareDocumentPosition(reader.querySelector('.note-reader-meta')!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(reader.querySelector('.note-reader-meta')!.compareDocumentPosition(reader.querySelector('.note-reader-body')!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(reader.textContent).not.toContain('Preview');
  });
  it('opens editable notes in their project with transient edit state', async () => {
    const { fixture } = await createGlobal('2');
    const link = fixture.debugElement.query(By.css('.note-reader-actions')).injector.get(RouterLink);
    expect(link.urlTree?.toString()).toBe('/projects/project/notes/2');
    expect(link.state).toEqual({ noteEdit: true });
    expect((fixture.nativeElement as HTMLElement).querySelector('.note-reader-actions')?.textContent).toContain('Edit note');
  });
  it('opens non-editable notes in read-only project mode', async () => {
    const { fixture } = await createGlobal('2');
    fixture.componentInstance.note.set({ ...fixture.componentInstance.note()!, archived_at: '2026-01-02' }); fixture.detectChanges();
    const link = fixture.debugElement.query(By.css('.note-reader-actions')).injector.get(RouterLink);
    expect(link.state).toBeUndefined();
    expect((fixture.nativeElement as HTMLElement).querySelector('.note-reader-actions')?.textContent).toContain('Open in project');
  });
});

async function createGlobal(noteId?: string, count = 2) {
  const params = new BehaviorSubject(convertToParamMap(noteId ? { noteId } : {}));
  const notes = Array.from({ length: count }, (_, index) => index === 1 ? { ...note(2), title: 'Second', markdown: 'contains needle', folder_id: 1 } : note(index + 1));
  const request = vi.fn((path: string) => path.startsWith('/api/projects?') ? Promise.resolve([{ id: 1, key: 'project', name: 'Project', role: 'MEMBER', notes_enabled: true, archived: false }]) : path.includes('note-folders') ? Promise.resolve([{ id: 1, project: 'project', parent_id: null, name: 'Folder' }, { id: 2, project: 'project', parent_id: 1, name: 'Nested folder' }]) : path.includes('/projects/project/notes') ? Promise.resolve(notes) : Promise.resolve(notes[1]));
  await TestBed.configureTestingModule({ imports: [GlobalNotesComponent], providers: [provideRouter([]), { provide: ActivatedRoute, useValue: { paramMap: params, get snapshot() { return { paramMap: params.value }; } } }, { provide: ApiService, useValue: { request } }, { provide: InspectionService, useValue: { active: () => false } }, { provide: MarkdownService, useValue: { render: () => '' } }] }).compileComponents();
  const fixture = TestBed.createComponent(GlobalNotesComponent); fixture.detectChanges(); await fixture.componentInstance.load(); fixture.detectChanges();
  return { fixture, request };
}

function note(id: number) { return { id, project: 'project', folder_id: null, title: 'Old note', markdown: '', version: 1, creator: 'User', updater: 'User', created_at: '2026-01-01', updated_at: '2026-01-01', archived_at: null }; }
