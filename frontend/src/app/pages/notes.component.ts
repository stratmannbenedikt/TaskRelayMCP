import { NgTemplateOutlet } from '@angular/common';
import { Component, effect, ElementRef, HostListener, inject, signal } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { ApiError, ApiService } from '../core/api.service';
import { InspectionService } from '../core/inspection.service';
import { MarkdownService } from '../core/markdown.service';
import { Note, NoteFolder, NoteRevision, Project } from '../models';
import { HeaderComponent } from '../shared/header.component';
import { RelativeTimePipe } from '../shared/relative-time.pipe';

@Component({
  imports: [NgTemplateOutlet, ReactiveFormsModule, RouterLink, HeaderComponent, RelativeTimePipe],
  template: `
    <main>
      <app-header />
      <p class="error">{{ error() }}</p>
      <section class="page-title"><h2>Notes</h2></section>
      <section class="notes-layout" [class.has-selected-note]="detail() && !editing()" [class.is-editing]="editing()">
        <aside class="folders">
          <h3 class="browse-notes-heading">Browse notes</h3>
          <label>Search<input [formControl]="search"></label>
          <label class="toggle"><input type="checkbox" [checked]="showArchived()" (change)="showArchived.set($any($event.target).checked); loadNotes()"> Show archived</label>
          <section class="project-note-tree" [class.drop-target]="canDrop(null)">
            <div class="tree-row project-tree-row">
              <button type="button" class="tree-control tree-toggle" [attr.aria-label]="(rootIsCollapsed() ? 'Expand ' : 'Collapse ') + project()?.name" [attr.aria-expanded]="!rootIsCollapsed()" (click)="rootCollapsed.update(value => !value)">{{ rootIsCollapsed() ? '▸' : '▾' }}</button>
              <span class="tree-name">{{ project()?.name }}</span>
              @if (writable()) {
                <span class="tree-row-actions"><button type="button" class="tree-control" aria-label="Add to project root" [attr.aria-expanded]="actionPanel() === 'root-add'" (click)="toggleAction('root-add')">+</button></span>
              }
            </div>
            @if (writable() && actionPanel() === 'root-add') {
              <div class="tree-action-panel tree-add-panel"><button (click)="closeAction(); newNote()">New note</button><button (click)="closeAction(); createFolder(null)">New folder</button></div>
            }
            @if (!rootIsCollapsed()) { <div class="tree-children"><ng-container [ngTemplateOutlet]="folder" [ngTemplateOutletContext]="{parent: null}"></ng-container></div> }
          </section>
        </aside>
        <section>
          @if (!detail()) {
            <section class="preview"><p>Select a note.</p></section>
          } @else if (editing()) {
            <section class="note-edit-workspace"><form [formGroup]="form" (ngSubmit)="save()">
              <label>Title<input formControlName="title" maxlength="240"></label>
              <label>Folder<select formControlName="folder_id"><option value="">Unfiled</option>@for (folder of folders(); track folder.id) { <option [value]="folder.id">{{ folder.name }}</option> }</select></label>
                <label for="markdown-editor">Markdown</label><div class="markdown-toolbar" role="toolbar" aria-label="Markdown formatting"><button type="button" title="Heading" aria-label="Heading" (click)="format(editor, 'heading')">Heading</button><button type="button" title="Bold" aria-label="Bold" (click)="format(editor, 'bold')">Bold</button><button type="button" title="Italic" aria-label="Italic" (click)="format(editor, 'italic')">Italic</button><button type="button" title="Link" aria-label="Link" (click)="format(editor, 'link')">Link</button><button type="button" title="Bulleted list" aria-label="Bulleted list" (click)="format(editor, 'bulleted-list')">Bulleted list</button><button type="button" title="Numbered list" aria-label="Numbered list" (click)="format(editor, 'numbered-list')">Numbered list</button><button type="button" title="Quote" aria-label="Quote" (click)="format(editor, 'quote')">Quote</button><button type="button" title="Code" aria-label="Code" (click)="format(editor, 'code')">Code</button><button type="button" title="Table" aria-label="Table" (click)="format(editor, 'table')">Table</button></div><textarea #editor id="markdown-editor" formControlName="markdown" maxlength="1048576"></textarea>
              <label>Insert note link<select (change)="insertLink(editor, $any($event.target).value); $any($event.target).value=''">
                <option value="">Choose note…</option>@for (item of notes(); track item.id) { <option [value]="item.id">N-{{ item.id }} {{ item.title }}</option> }
              </select></label>
              <button [disabled]="form.invalid">Save</button><button type="button" class="quiet" (click)="cancel()">Cancel</button>
              @if (conflict()) { <p class="error">This note changed elsewhere. Reload before saving.</p><button type="button" (click)="loadNote()">Reload</button> }
            </form><section class="preview note-edit-preview"><h3>Preview</h3><div [innerHTML]="render(form.controls.markdown.value)"></div></section></section>
          } @else if (note(); as selected) {
            <article class="note-reader preview">
              <header class="note-reader-header"><h3>{{ selected.title }}</h3><span class="note-reader-actions">@if (canEdit()) { <button (click)="edit()">Edit</button> } @if (canManage()) { <button class="quiet" (click)="archive()">{{ selected.archived_at ? 'Unarchive' : 'Archive' }}</button> }</span></header><p class="note-reader-meta"><small>{{ folderPath(selected.folder_id) }} · Updated by {{ selected.updater || 'Unknown' }} <time [attr.datetime]="selected.updated_at" [title]="selected.updated_at">{{ selected.updated_at | relativeTime }}</time></small></p>
              <div class="note-reader-body" [innerHTML]="render(selected.markdown)"></div>
              @if (selected.backlinks?.length) {
                <section class="note-reader-backlinks"><h4>Backlinks</h4>@for (link of selected.backlinks; track link.id) { <a [routerLink]="['/projects', key(), 'notes', link.id]">N-{{ link.id }} {{ link.title }}</a> }</section>
              }
              @if (revisions().length) {
                <section class="note-reader-revisions"><h4>Revisions</h4>
                @for (revision of revisions(); track revision.version) {
                  <p>Version {{ revision.version }} · {{ revision.editor }} · <time [attr.datetime]="revision.created_at" [title]="revision.created_at">{{ revision.created_at | relativeTime }}</time> @if (canManage()) { <button class="link" (click)="restore(revision.version)">Restore</button> }</p>
                }
                </section>
              }
            </article>
          }
        </section>
      </section>
      <ng-template #folder let-parent="parent">
        @for (item of children(parent); track item.id) {
          <div class="folder-tree" [attr.data-folder-id]="item.id" [class.dragging]="dragging()?.kind === 'folder' && dragging()?.id === item.id" [class.drop-target]="canDrop(item.id)">
            <div class="tree-row">
              <button type="button" class="tree-control tree-toggle" [attr.aria-label]="(collapsed(item.id) ? 'Expand ' : 'Collapse ') + item.name" [attr.aria-expanded]="!collapsed(item.id)" (click)="toggleCollapsed(item.id)">{{ collapsed(item.id) ? '▸' : '▾' }}</button>
              @if (writable()) { <span class="tree-drag-handle" aria-hidden="true" draggable="true" [title]="'Drag ' + item.name" [attr.data-drag-folder]="item.id">⠿</span> }
              <span class="tree-marker tree-folder-marker" aria-hidden="true"></span><span class="tree-name">{{ item.name }}</span>
              @if (writable()) {
                <span class="tree-row-actions"><button type="button" class="tree-control" [attr.aria-label]="'Add to ' + item.name" [attr.aria-expanded]="actionPanel() === item.id + '-add'" (click)="toggleAction(item.id + '-add')">+</button><button type="button" class="tree-control" [attr.aria-label]="'Manage ' + item.name" [attr.aria-expanded]="actionPanel() === item.id + '-manage'" (click)="toggleAction(item.id + '-manage')">…</button></span>
              }
            </div>
            @if (writable() && actionPanel() === item.id + '-add') { <div class="tree-action-panel tree-add-panel"><button (click)="closeAction(); newNote(item.id)">New note</button><button (click)="closeAction(); createFolder(item.id)">New folder</button></div> }
            @if (writable() && actionPanel() === item.id + '-manage') {
              <div class="tree-action-panel tree-manage-panel"><button (click)="closeAction(); renameFolder(item)">Rename</button><label>Move<select [value]="item.parent_id ?? ''" (change)="closeAction(); moveFolder(item, $any($event.target).value)"><option value="">Root</option>@for (parent of parents(item); track parent.id) { <option [value]="parent.id">{{ parent.name }}</option> }</select></label><button class="danger" (click)="closeAction(); deleteFolder(item)">Delete</button></div>
            }
            @if (!collapsed(item.id)) { <div class="tree-children"><ng-container [ngTemplateOutlet]="folder" [ngTemplateOutletContext]="{parent: item.id}"></ng-container></div> }
          </div>
        }
        @for (item of notesAt(parent); track item.id) {
          <div class="note-tree-row" [class.selected]="noteId() === item.id" [class.dragging]="dragging()?.kind === 'note' && dragging()?.id === item.id">
            @if (writable() && !item.archived_at) { <span class="tree-drag-handle" aria-hidden="true" draggable="true" [title]="'Drag ' + item.title" [attr.data-drag-note]="item.id">⠿</span> }
            <span class="tree-marker tree-note-marker" aria-hidden="true"></span><a class="note-tree" [class.selected]="noteId() === item.id" [attr.aria-current]="noteId() === item.id ? 'page' : null" [routerLink]="['/projects', key(), 'notes', item.id]">{{ item.title }}</a>
          </div>
        }
      </ng-template>
    </main>
  `,
})
export class NotesComponent {
  private api = inject(ApiService); private route = inject(ActivatedRoute); private router = inject(Router); private noteEdit?: number; private inspectionActive = false; private markdown = inject(MarkdownService); private host = inject(ElementRef) as ElementRef<HTMLElement>; readonly inspection = inject(InspectionService); readonly project = signal<Project | undefined>(undefined); readonly folders = signal<NoteFolder[]>([]); readonly notes = signal<Note[]>([]); readonly note = signal<Note | undefined>(undefined); readonly revisions = signal<NoteRevision[]>([]); readonly showArchived = signal(false); readonly editing = signal(false); readonly error = signal(''); readonly conflict = signal(false); readonly dragging = signal<{ kind: 'folder' | 'note'; id: number } | undefined>(undefined); readonly rootCollapsed = signal(false); readonly collapsedFolders = signal<Set<number>>(new Set()); readonly actionPanel = signal<string | undefined>(undefined); readonly search = new FormControl('', { nonNullable: true }); readonly searchActive = signal(false);
  readonly form = new FormGroup({ title: new FormControl('', { nonNullable: true, validators: Validators.required }), markdown: new FormControl('', { nonNullable: true }), folder_id: new FormControl('', { nonNullable: true }) });
  constructor() { this.noteEdit = this.router.getCurrentNavigation()?.extras.state?.['noteEdit'] === true ? this.noteId() : undefined; this.inspectionActive = this.inspection.active(); effect(() => { const active = this.inspection.active(); if (active !== this.inspectionActive) void this.inspectionChanged(active); }); this.route.paramMap.subscribe(() => void this.load()); this.search.valueChanges.subscribe(value => { this.searchActive.set(!!value.trim()); void this.loadNotes(); }); }
  key() { return this.route.snapshot.paramMap.get('key')!; } draft() { return this.route.snapshot.data['draft'] === true; } noteId() { const id = this.route.snapshot.paramMap.get('noteId'); return id ? Number(id) : undefined; } detail() { return this.draft() || !!this.noteId(); } writable() { return !!this.project()?.role && !this.project()?.archived && !this.inspection.active(); } canEdit() { return this.writable() && !this.note()?.archived_at; } canManage() { return this.writable() && !this.editing(); }
  async load() { const noteEdit = this.noteEdit, noteId = this.noteId(); this.noteEdit = undefined; try { this.editing.set(false); this.note.set(undefined); this.revisions.set([]); const projects = await this.api.request<Project[]>(`/api/projects?inspection=${this.inspection.active()}&include_archived=true`); const project = projects.find(p => p.key === this.key()); if (project && !project.notes_enabled) { await this.router.navigateByUrl(`/projects/${this.key()}/tasks`, { replaceUrl: true }); return; } this.project.set(project); await Promise.all([this.loadFolders(), this.loadNotes()]); if (noteId) { await this.loadNote(); if (noteEdit === noteId && this.note()?.id === noteId && this.canEdit()) this.editing.set(true); } else if (this.draft() && this.writable()) { this.form.reset({ title: '', markdown: '', folder_id: this.route.snapshot.queryParamMap.get('folder_id') ?? '' }); this.form.markAsPristine(); this.editing.set(true); } } catch (e) { this.error.set(e instanceof Error ? e.message : 'Request failed'); } }
  private async inspectionChanged(active: boolean) { if (active && this.editing() && this.form.dirty && !this.canDeactivate()) { this.inspection.toggle(false); return; } this.inspectionActive = active; if (active) this.editing.set(false); await this.load(); }
  async loadFolders() { this.folders.set(await this.api.request<NoteFolder[]>(`/api/projects/${this.key()}/note-folders?inspection=${this.inspection.active()}`)); }
  async loadNotes() { const q = this.search.value; const notes = await this.api.request<Note[]>(`/api/projects/${this.key()}/notes?inspection=${this.inspection.active()}${q ? `&q=${encodeURIComponent(q)}` : ''}`); this.notes.set(notes.filter(n => this.showArchived() || !n.archived_at)); }
  async loadNote() { const note = await this.api.request<Note>(`/api/notes/${this.noteId()}?inspection=${this.inspection.active()}`); this.note.set(note); this.form.reset({ title: note.title, markdown: note.markdown, folder_id: note.folder_id?.toString() ?? '' }); this.form.markAsPristine(); this.revisions.set(await this.api.request<NoteRevision[]>(`/api/notes/${note.id}/revisions?inspection=${this.inspection.active()}`)); this.conflict.set(false); }
  children(parent: number | null) { return this.folders().filter(folder => folder.parent_id === parent); } notesAt(parent: number | null) { return this.notes().filter(note => note.folder_id === parent); } rootIsCollapsed() { return !this.searchActive() && this.rootCollapsed(); } collapsed(id: number) { return !this.searchActive() && this.collapsedFolders().has(id); } toggleCollapsed(id: number) { const collapsed = new Set(this.collapsedFolders()); collapsed.has(id) ? collapsed.delete(id) : collapsed.add(id); this.collapsedFolders.set(collapsed); } toggleAction(key: string) { this.actionPanel.update(open => open === key ? undefined : key); } closeAction() { this.actionPanel.set(undefined); } parents(folder: NoteFolder) { return this.folders().filter(item => item.id !== folder.id && !this.descends(item, folder.id)); } private descends(folder: NoteFolder, ancestor: number): boolean { let parent = folder.parent_id; while (parent) { if (parent === ancestor) return true; parent = this.folders().find(f => f.id === parent)?.parent_id ?? null; } return false; } folderPath(id: number | null) { if (!id) return 'Unfiled'; const names: string[] = []; let folder = this.folders().find(item => item.id === id); while (folder) { names.unshift(folder.name); folder = folder.parent_id ? this.folders().find(item => item.id === folder!.parent_id) : undefined; } return names.join(' / '); }
  async createFolder(parent: number | null) { const name = prompt('Folder name')?.trim(); if (!this.writable() || !name) return; await this.run(() => this.api.request(`/api/projects/${this.key()}/note-folders`, { method: 'POST', body: { name, parent_id: parent } })); }
  async renameFolder(folder: NoteFolder) { const name = prompt('Folder name', folder.name)?.trim(); if (name) await this.run(() => this.api.request(`/api/note-folders/${folder.id}`, { method: 'PATCH', body: { name } })); }
  async moveFolder(folder: NoteFolder, parent: string) { if (!this.writable() || (parent && !this.parents(folder).some(p => p.id === Number(parent)))) return; await this.run(() => this.api.request(`/api/note-folders/${folder.id}`, { method: 'PATCH', body: { parent_id: parent ? Number(parent) : null } })); }
  ngAfterViewChecked() { this.host.nativeElement.querySelector('.project-note-tree')?.classList.toggle('drop-target', this.canDrop(null)); }
  @HostListener('dragstart', ['$event']) onDragStart(event: DragEvent) { const source = (event.target as Element).closest<HTMLElement>('[data-drag-folder], [data-drag-note]'); if (!source) return; this.startDrag(event, { kind: source.dataset['dragFolder'] ? 'folder' : 'note', id: Number(source.dataset['dragFolder'] ?? source.dataset['dragNote']) }); }
  @HostListener('dragend') onDragEnd() { this.endDrag(); }
  @HostListener('dragover', ['$event']) onDragOver(event: DragEvent) { const target = this.dropTarget(event); if (target === undefined || !this.canDrop(target)) return; event.preventDefault(); if (event.dataTransfer) event.dataTransfer.dropEffect = 'move'; }
  @HostListener('drop', ['$event']) async onDrop(event: DragEvent) { const target = this.dropTarget(event); if (target !== undefined) await this.drop(event, target); }
  startDrag(event: DragEvent, payload: { kind: 'folder' | 'note'; id: number }) { if (!this.writable()) return; this.dragging.set(payload); event.dataTransfer?.setData('text/plain', `${payload.kind}:${payload.id}`); if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move'; }
  endDrag() { this.dragging.set(undefined); }
  canDrop(parent: number | null) { const payload = this.dragging(); if (!this.writable() || !payload) return false; if (payload.kind === 'folder') { const folder = this.folders().find(item => item.id === payload.id); return !!folder && folder.parent_id !== parent && (parent === null || this.parents(folder).some(item => item.id === parent)); } const note = this.notes().find(item => item.id === payload.id); return !!note && !note.archived_at && note.folder_id !== parent; }
  async drop(event: DragEvent, parent: number | null) { if (!this.canDrop(parent)) return; event.preventDefault(); event.stopPropagation(); const payload = this.dragging()!; this.endDrag(); if (payload.kind === 'folder') { const folder = this.folders().find(item => item.id === payload.id); if (folder) await this.moveFolder(folder, parent?.toString() ?? ''); return; } const note = this.notes().find(item => item.id === payload.id); if (note) await this.run(() => this.api.request(`/api/notes/${note.id}`, { method: 'PATCH', body: { title: note.title, markdown: note.markdown, folder_id: parent, expected_version: note.version } })); }
  private dropTarget(event: DragEvent) { const target = (event.target as Element).closest<HTMLElement>('.folder-tree, .project-note-tree'); return target ? (target.dataset['folderId'] ? Number(target.dataset['folderId']) : null) : undefined; }
  async deleteFolder(folder: NoteFolder) { if (confirm(`Delete empty folder “${folder.name}”?`)) await this.run(() => this.api.request(`/api/note-folders/${folder.id}`, { method: 'DELETE' })); }
  async newNote(folder?: number) { if (this.writable()) await this.router.navigate(['/projects', this.key(), 'notes', 'new'], folder ? { queryParams: { folder_id: folder } } : undefined); }
  edit() { if (this.canEdit()) this.editing.set(true); }
  async save() { if (!this.writable() || this.form.invalid) return; this.conflict.set(false); try { const v = this.form.getRawValue(), body = { ...v, folder_id: v.folder_id ? Number(v.folder_id) : null }; if (this.draft()) { const note = await this.api.request<Note>(`/api/projects/${this.key()}/notes`, { method: 'POST', body }); this.form.markAsPristine(); await this.router.navigate(['/projects', this.key(), 'notes', note.id]); return; } const note = this.note(); if (!note) return; await this.api.request<Note>(`/api/notes/${note.id}`, { method: 'PATCH', body: { ...body, expected_version: note.version } }); this.editing.set(false); await this.loadNote(); } catch (e) { if (e instanceof ApiError && e.status === 409) this.conflict.set(true); else this.error.set(e instanceof Error ? e.message : 'Request failed'); } }
  async cancel() { if (!this.canDeactivate()) return; this.form.markAsPristine(); if (this.draft()) await this.router.navigate(['/projects', this.key(), 'notes']); else this.editing.set(false); }
  canDeactivate() { return !this.editing() || !this.form.dirty || confirm('Discard unsaved note changes?'); }
  @HostListener('window:beforeunload', ['$event']) beforeUnload(event: BeforeUnloadEvent) { if (this.editing() && this.form.dirty) event.preventDefault(); }
  async archive() { const note = this.note(); if (note && this.canManage() && (note.archived_at || confirm('Archive this note?'))) await this.run(() => this.api.request(`/api/notes/${note.id}`, { method: 'PATCH', body: { archived: !note.archived_at, expected_version: note.version } })); }
  async restore(version: number) { const note = this.note(); if (note && this.canManage() && confirm(`Restore version ${version}?`)) await this.run(() => this.api.request(`/api/notes/${note.id}/revisions/${version}/restore`, { method: 'POST', body: { expected_version: note.version } })); }
  format(editor: HTMLTextAreaElement, action: 'heading' | 'bold' | 'italic' | 'link' | 'bulleted-list' | 'numbered-list' | 'quote' | 'code' | 'table') {
    const selected = editor.value.slice(editor.selectionStart, editor.selectionEnd);
    if (action === 'heading') return this.prefix(editor, '# ');
    if (action === 'bulleted-list') return this.prefix(editor, '- ');
    if (action === 'numbered-list') return this.prefix(editor, '1. ');
    if (action === 'quote') return this.prefix(editor, '> ');
    if (action === 'table') return this.replace(editor, `${editor.selectionStart && !editor.value.slice(0, editor.selectionStart).endsWith('\n') ? '\n\n' : ''}| Header 1 | Header 2 |\n| --- | --- |\n| Cell 1 | Cell 2 |`);
    if (action === 'code') return selected && !selected.includes('\n') ? this.wrap(editor, '`', '`', 'code') : this.wrap(editor, '```\n', '\n```', 'code');
    return action === 'bold' ? this.wrap(editor, '**', '**', 'bold text') : action === 'italic' ? this.wrap(editor, '_', '_', 'italic text') : this.wrap(editor, '[', '](https://)', 'link text');
  }
  insertLink(editor: HTMLTextAreaElement, id: string) { if (id) this.replace(editor, `[[N-${id}]]`); }
  private prefix(editor: HTMLTextAreaElement, prefix: string) { const start = editor.selectionStart, end = editor.selectionEnd, value = editor.value, first = value.lastIndexOf('\n', start - 1) + 1, last = value.indexOf('\n', end), finish = last < 0 ? value.length : last, selected = value.slice(first, finish); this.replace(editor, selected.split('\n').map(line => prefix + line).join('\n'), start - first + prefix.length, end - first + prefix.length * selected.split('\n').length, first, finish); }
  private wrap(editor: HTMLTextAreaElement, before: string, after: string, placeholder: string) { const selected = editor.value.slice(editor.selectionStart, editor.selectionEnd); this.replace(editor, before + (selected || placeholder) + after, before.length, before.length + (selected || placeholder).length); }
  private replace(editor: HTMLTextAreaElement, replacement: string, selectionStart = replacement.length, selectionEnd = selectionStart, start = editor.selectionStart, end = editor.selectionEnd) { const value = editor.value, next = value.slice(0, start) + replacement + value.slice(end), maxLength = editor.maxLength < 0 ? 1048576 : editor.maxLength; if (next.length > maxLength) return; this.form.controls.markdown.setValue(next); this.form.controls.markdown.markAsDirty(); queueMicrotask(() => { editor.focus(); editor.setSelectionRange(start + selectionStart, start + selectionEnd); }); }
  render(value: string) { return (this.markdown || new MarkdownService()).render(value, this.note()?.references || [], id => `/projects/${this.key()}/notes/${id}`); }
  private async run(action: () => Promise<unknown>) { try { await action(); await this.load(); } catch (e) { this.error.set(e instanceof Error ? e.message : 'Request failed'); } }
}
