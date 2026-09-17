import { Component, computed, effect, inject, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { ApiService } from '../core/api.service';
import { AuthService } from '../core/auth.service';
import { InspectionService } from '../core/inspection.service';
import { Project, Tag, Task } from '../models';
import { HeaderComponent } from '../shared/header.component';
import { TaskFilterBarComponent } from '../shared/task-filter-bar.component';
import { defaultTaskFilter, filterTasks, TaskFilter } from '../shared/task-filters';
import { TaskTableComponent } from '../shared/task-table.component';

@Component({ imports: [HeaderComponent, TaskFilterBarComponent, TaskTableComponent], template: `<main><app-header /><h2>Tasks</h2><p class="error">{{ error() }}</p><app-task-filter-bar [showProject]="true" [projects]="projects()" [tags]="tags()" [state]="filter()" (apply)="apply($event)" (resetFilters)="reset()" /><app-task-table [tasks]="visible()" [projects]="projects()" [showProject]="true" (open)="open($event)" (tagClick)="filterTag($event)" /></main>` })
export class GlobalTasksComponent {
  private api = inject(ApiService); private route = inject(ActivatedRoute); private router = inject(Router); private auth = inject(AuthService); readonly inspection = inject(InspectionService); readonly projects = signal<Project[]>([]); readonly tasks = signal<Task[]>([]); readonly tags = signal<Tag[]>([]); readonly error = signal(''); readonly filter = signal<TaskFilter>(defaultTaskFilter());
  readonly visible = computed(() => filterTasks(this.tasks(), this.filter(), this.auth.user()?.display_name));
  constructor() { effect(() => { this.inspection.active(); void this.load(); }); this.route.queryParamMap.subscribe(query => this.filter.set({ q: query.get('q') || '', project: query.get('project') || '', status: query.get('status') ?? 'TODO', priority: query.get('priority') || '', assignment: query.get('assignment') || 'all', sort: query.get('sort') || 'priority', tagIds: query.getAll('tag').map(Number).filter(Number.isInteger) })); }
  async load() { try { const inspection = this.inspection.active(), [tasks, projects, tags] = await Promise.all([this.api.request<Task[]>(`/api/tasks?inspection=${inspection}&limit=200`), this.api.request<Project[]>(`/api/projects?inspection=${inspection}&include_archived=false`), this.api.request<Tag[]>(`/api/tags?inspection=${inspection}`)]); this.tasks.set(tasks); this.projects.set(projects); this.tags.set(tags); } catch (error) { this.error.set(error instanceof Error ? error.message : 'Request failed'); } }
  apply(filter: TaskFilter) { const state = { ...filter, tagIds: [...filter.tagIds] }; this.filter.set(state); void this.router.navigate([], { relativeTo: this.route, queryParams: { q: state.q || null, project: state.project || null, status: state.status || null, priority: state.priority || null, assignment: state.assignment === 'all' ? null : state.assignment, sort: state.sort === 'priority' ? null : state.sort, tag: state.tagIds.length ? state.tagIds : null } }); }
  reset() { this.apply({ ...defaultTaskFilter(), tagIds: [] }); this.filter.set(defaultTaskFilter()); void this.router.navigate([], { relativeTo: this.route, queryParams: {} }); }
  filterTag(id: number) { this.apply({ ...this.filter(), tagIds: [id] }); }
  open(task: Task) { return this.router.navigateByUrl(`/projects/${task.target_project}/tasks/${task.id}`); }
}
