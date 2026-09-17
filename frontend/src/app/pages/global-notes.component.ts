import { NgTemplateOutlet } from '@angular/common';
import { Component, effect, inject, signal } from '@angular/core';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { ApiService } from '../core/api.service';
import { InspectionService } from '../core/inspection.service';
import { MarkdownService } from '../core/markdown.service';
import { Note, NoteFolder, Project } from '../models';
import { HeaderComponent } from '../shared/header.component';
import { RelativeTimePipe } from '../shared/relative-time.pipe';

interface NoteTree { project: Project; folders: NoteFolder[]; notes: Note[]; truncated?: boolean; error?: string; }

@Component({
  imports: [NgTemplateOutlet, ReactiveFormsModule, RouterLink, HeaderComponent, RelativeTimePipe],
  template: `
    <main><app-header /><h2>Notes</h2><p class="error">{{ error() }}</p>
      <section class="notes-layout" [class.has-selected-note]="!!note()">
        <aside class="folders">
          <h3 class="browse-notes-heading">Browse notes</h3>
          <label>Search<input [formControl]="search"></label>
          @for (tree of trees(); track tree.project.id) {
            <section class="project-note-tree">
              <div class="tree-row project-tree-row"><button type="button" class="tree-control tree-toggle" [attr.aria-label]="(collapsed(projectKey(tree)) ? 'Expand ' : 'Collapse ') + tree.project.name" [attr.aria-expanded]="!collapsed(projectKey(tree))" (click)="toggle(projectKey(tree))">{{ collapsed(projectKey(tree)) ? '▸' : '▾' }}</button><span class="tree-name">{{ tree.project.name }}</span></div>
              @if (tree.error) { <small class="error">{{ tree.error }}</small> } @else { @if (tree.truncated) { <small class="tree-limit-notice">Only 200 notes are loaded. Search older notes in the project Notes view.</small> } @if (!collapsed(projectKey(tree))) { <div class="tree-children"><ng-container [ngTemplateOutlet]="folder" [ngTemplateOutletContext]="{tree: tree, parent: null}"></ng-container></div> } }
            </section>
          }
        </aside>
        <section class="note-reader preview">
          @if (note(); as selected) {
            <header class="note-reader-header"><h3>{{ selected.title }}</h3><a class="note-reader-actions" [routerLink]="['/projects', selected.project, 'notes', selected.id]" [state]="canEdit(selected) ? { noteEdit: true } : undefined">{{ canEdit(selected) ? 'Edit note' : 'Open in project' }}</a></header><p class="note-reader-meta">{{ selected.project }} · Updated by {{ selected.updater || 'Unknown' }} <time [attr.datetime]="selected.updated_at" [title]="selected.updated_at">{{ selected.updated_at | relativeTime }}</time></p><div class="note-reader-body" [innerHTML]="markdown.render(selected.markdown, selected.references || [])"></div>
            @if (selected.backlinks?.length) { <section class="note-reader-backlinks"><h4>Backlinks</h4>@for (link of selected.backlinks; track link.id) { <a [routerLink]="['/notes', link.id]">N-{{ link.id }} {{ link.title }}</a> }</section> }
          } @else { <p>Select a note.</p> }
        </section>
      </section>
      <ng-template #folder let-tree="tree" let-parent="parent">
        @for (item of children(tree, parent); track item.id) {
          <div class="folder-tree"><div class="tree-row"><button type="button" class="tree-control tree-toggle" [attr.aria-label]="(collapsed(folderKey(tree, item.id)) ? 'Expand ' : 'Collapse ') + item.name" [attr.aria-expanded]="!collapsed(folderKey(tree, item.id))" (click)="toggle(folderKey(tree, item.id))">{{ collapsed(folderKey(tree, item.id)) ? '▸' : '▾' }}</button><span class="tree-marker tree-folder-marker" aria-hidden="true"></span><span class="tree-name">{{ item.name }}</span></div>
            @if (!collapsed(folderKey(tree, item.id))) { <div class="tree-children"><ng-container [ngTemplateOutlet]="folder" [ngTemplateOutletContext]="{tree: tree, parent: item.id}"></ng-container></div> }
          </div>
        }
        @for (item of notes(tree, parent); track item.id) { <div class="note-tree-row" [class.selected]="noteId() === item.id"><span class="tree-marker tree-note-marker" aria-hidden="true"></span><a class="note-tree" [class.selected]="noteId() === item.id" [attr.aria-current]="noteId() === item.id ? 'page' : null" [routerLink]="['/notes', item.id]">{{ item.title }}</a></div> }
      </ng-template>
    </main>
  `,
})
export class GlobalNotesComponent {
  private api = inject(ApiService); private route = inject(ActivatedRoute); readonly inspection = inject(InspectionService); readonly markdown = inject(MarkdownService); readonly trees = signal<NoteTree[]>([]); readonly note = signal<Note | undefined>(undefined); readonly error = signal(''); readonly collapsedItems = signal<Set<string>>(new Set()); readonly search = new FormControl('', { nonNullable: true }); readonly searchActive = signal(false);
  constructor() { effect(() => { this.inspection.active(); void this.load(); }); this.route.paramMap.subscribe(() => void this.loadNote()); this.search.valueChanges.subscribe(value => this.searchActive.set(!!value.trim())); }
  noteId() { const id = this.route.snapshot.paramMap.get('noteId'); return id ? Number(id) : undefined; } projectKey(tree: NoteTree) { return `project:${tree.project.key}`; } folderKey(tree: NoteTree, id: number) { return `${tree.project.key}:${id}`; } collapsed(key: string) { return !this.searchActive() && this.collapsedItems().has(key); } toggle(key: string) { const items = new Set(this.collapsedItems()); items.has(key) ? items.delete(key) : items.add(key); this.collapsedItems.set(items); }
  children(tree: NoteTree, parent: number | null) { return tree.folders.filter(f => f.parent_id === parent); } notes(tree: NoteTree, parent: number | null) { const query = this.search.value.trim().toLocaleLowerCase(); return tree.notes.filter(note => note.folder_id === parent && (!query || `${note.title}\n${note.markdown}`.toLocaleLowerCase().includes(query))); }
  canEdit(note: Note) { const project = this.trees().find(tree => tree.project.key === note.project)?.project; return !!project?.role && !project.archived && !this.inspection.active() && !note.archived_at; }
  async load() { try { const inspection = this.inspection.active(), projects = (await this.api.request<Project[]>(`/api/projects?inspection=${inspection}&include_archived=false`)).filter(p => p.notes_enabled && !p.archived); // ponytail: replace with aggregate endpoint only if measured project count makes fan-out problematic.
    this.trees.set(await Promise.all(projects.map(async project => { try { const [folders, notes] = await Promise.all([this.api.request<NoteFolder[]>(`/api/projects/${project.key}/note-folders?inspection=${inspection}`), this.api.request<Note[]>(`/api/projects/${project.key}/notes?inspection=${inspection}&limit=200`)]); return { project, folders, notes: notes.filter(n => !n.archived_at), truncated: notes.length === 200 }; } catch (e) { return { project, folders: [], notes: [], error: e instanceof Error ? e.message : 'Could not load notes' }; } })));
    await this.loadNote();
  } catch (e) { this.error.set(e instanceof Error ? e.message : 'Request failed'); } }
  private async loadNote() { const id = this.route.snapshot.paramMap.get('noteId'); this.note.set(undefined); this.error.set(''); if (!id) return; try { this.note.set(await this.api.request<Note>(`/api/notes/${id}?inspection=${this.inspection.active()}`)); } catch (e) { this.error.set(e instanceof Error ? e.message : 'Request failed'); } }
}
