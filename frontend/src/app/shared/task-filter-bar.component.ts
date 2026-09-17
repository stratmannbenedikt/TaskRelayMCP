import { Component, EventEmitter, Input, OnChanges, OnDestroy, Output, signal } from '@angular/core';
import { NgStyle } from '@angular/common';
import { FormControl, FormGroup, ReactiveFormsModule } from '@angular/forms';
import { Project, Tag } from '../models';
import { defaultTaskFilter, TaskFilter } from './task-filters';
import { tagStyle } from './tag-colors';

@Component({ selector: 'app-task-filter-bar', imports: [NgStyle, ReactiveFormsModule], template: `
<button type="button" class="filter-toggle" [attr.aria-expanded]="filtersOpen()" aria-controls="task-filter-body" (click)="filtersOpen.update(open => !open)">Filters@if (activeFilterCount()) { ({{ activeFilterCount() }}) }</button>
<form class="filters" [class.with-project]="showProject" [formGroup]="form" (change)="apply.emit(value())" (ngSubmit)="apply.emit(value())">
  <div id="task-filter-body" class="filter-body" [hidden]="!desktop() && !filtersOpen()" [attr.inert]="!desktop() && !filtersOpen() ? '' : null">
   <label class="filter-text">Text<input formControlName="q"></label>
   @if (showProject) { <label class="filter-project">Project<select formControlName="project" (change)="clearTags()"><option value="">All</option>@for (project of projects; track project.key) { <option [value]="project.key">{{ project.name }}</option> }</select></label> }
   <label class="filter-status">Status<select formControlName="status"><option value="TODO">TODO</option><option value="DONE">DONE</option><option value="">All</option></select></label>
   <label class="filter-priority">Priority<select formControlName="priority"><option value="">All</option><option value="URGENT">URGENT</option><option value="HIGH">HIGH</option><option value="NORMAL">NORMAL</option><option value="LOW">LOW</option></select></label>
   <label class="filter-assignment">Assignment<select formControlName="assignment"><option value="all">All</option><option value="mine">Mine</option><option value="unassigned">Unassigned</option></select></label>
   <fieldset class="tag-picker filter-tags"><legend>Tags</legend>@for (tag of availableTags; track tag.id) { <button type="button" class="tag-chip" [ngStyle]="style(tag.color)" [attr.aria-pressed]="tagIds.includes(tag.id)" (click)="toggle(tag.id)">@if (tagIds.includes(tag.id)) { ✓ } {{ tag.name }}</button> }</fieldset>
   <label class="filter-sort">Sort<select formControlName="sort"><option value="priority">Priority</option><option value="recent">Recent update</option><option value="oldest">Oldest TODO</option><option value="newest">Newest</option><option value="project">Project</option></select></label><span class="filter-actions"><button>Apply</button><button type="button" class="quiet" (click)="resetFilters.emit()">Reset</button></span>
  </div>
</form>` })
export class TaskFilterBarComponent implements OnChanges, OnDestroy {
  private media?: MediaQueryList; private mediaListener?: () => void;
  @Input() showProject = false; @Input() projects: Project[] = []; @Input() tags: Tag[] = []; @Input() state: TaskFilter = defaultTaskFilter(); @Output() apply = new EventEmitter<TaskFilter>(); @Output() resetFilters = new EventEmitter<void>();
  readonly form = new FormGroup({ q: new FormControl('', { nonNullable: true }), project: new FormControl('', { nonNullable: true }), status: new FormControl('TODO', { nonNullable: true }), priority: new FormControl('', { nonNullable: true }), assignment: new FormControl('all', { nonNullable: true }), sort: new FormControl('priority', { nonNullable: true }), tagIds: new FormControl<number[]>([], { nonNullable: true }) });
  readonly desktop = signal(true); readonly filtersOpen = signal(true);
  constructor() { if (typeof matchMedia !== 'undefined') { this.media = matchMedia('(min-width: 701px)'); this.mediaListener = () => { this.desktop.set(this.media!.matches); if (this.media!.matches) this.filtersOpen.set(true); else this.filtersOpen.set(false); }; this.mediaListener(); this.media.addEventListener('change', this.mediaListener); } }
  ngOnDestroy() { if (this.mediaListener) this.media?.removeEventListener('change', this.mediaListener); }
  get tagIds() { return this.form.controls.tagIds.value; }
  ngOnChanges() { this.form.reset({ ...defaultTaskFilter(), ...this.state, tagIds: [...this.state.tagIds] }); }
  activeFilterCount() { return Number(!!this.state.q) + Number(this.showProject && !!this.state.project) + Number(this.state.status !== 'TODO') + Number(!!this.state.priority) + Number(this.state.assignment !== 'all') + this.state.tagIds.length + Number(this.state.sort !== 'priority'); }
  get availableTags() { return this.tags.filter(tag => !tag.archived_at && (!this.showProject || !this.form.controls.project.value || tag.project === this.form.controls.project.value)); }
  style(color: string) { return tagStyle(color); }
  toggle(id: number) { this.form.controls.tagIds.setValue(this.tagIds.includes(id) ? this.tagIds.filter(tag => tag !== id) : [...this.tagIds, id]); }
  clearTags() { this.form.controls.tagIds.setValue([]); }
  value(): TaskFilter { return { ...this.form.getRawValue(), tagIds: [...this.tagIds], ...(this.showProject ? {} : { project: this.state.project || '' }) }; }
}
