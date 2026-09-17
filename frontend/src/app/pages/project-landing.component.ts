import { Component, inject } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { ApiService } from '../core/api.service';
import { InspectionService } from '../core/inspection.service';
import { Project } from '../models';
@Component({ template: '<main><p>Loading project…</p></main>' })
export class ProjectLandingComponent { constructor() { const api = inject(ApiService), route = inject(ActivatedRoute), router = inject(Router), inspection = inject(InspectionService); const key = route.snapshot.paramMap.get('key')!; void api.request<Project[]>(`/api/projects?inspection=${inspection.active()}&include_archived=true`).then(projects => { const project = projects.find(item => item.key === key); return router.navigateByUrl(project ? `/projects/${key}/${project.tasks_enabled ? 'tasks' : 'notes'}` : '/home', { replaceUrl: true }); }).catch(() => router.navigateByUrl('/home', { replaceUrl: true })); } }
