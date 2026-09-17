import { Component, OnDestroy, inject, signal } from '@angular/core';
import { Router, RouterLink, RouterLinkActive } from '@angular/router';
import { ApiService } from '../core/api.service';
import { AuthService } from '../core/auth.service';
import { InspectionService } from '../core/inspection.service';
import { Project } from '../models';

@Component({
  selector: 'app-header',
  imports: [RouterLink, RouterLinkActive],
  template: `
    <header><button class="quiet menu" (click)="toggleDrawer()" aria-label="Toggle navigation">☰</button><h1>Task<strong>Relay</strong><sub>v0.5.0</sub></h1></header>
    <aside class="sidebar" [class.open]="drawer()" [attr.aria-hidden]="!drawer()" [attr.inert]="!drawer() ? '' : null">
      <nav class="primary-nav"><a routerLink="/home" routerLinkActive="active" (click)="closeDrawer()">Home</a><a routerLink="/tasks" routerLinkActive="active" (click)="closeDrawer()">Tasks</a><a routerLink="/notes" routerLinkActive="active" (click)="closeDrawer()">Notes</a></nav>
      <section class="my-projects"><h2>My Projects</h2>
        @for (project of projects(); track project.id) {
          <article class="sidebar-project" [style.border-color]="project.color || 'var(--accent)'"><div class="project-title-row"><strong [style.color]="titleColor(project.color)">{{ project.name }}</strong>@if (project.role === 'OWNER') { <a class="project-settings-cog" [routerLink]="['/projects', project.key, 'settings']" [attr.aria-label]="'Settings for ' + project.name" (click)="closeDrawer()">⚙</a> }</div><div class="project-capabilities">@if (project.tasks_enabled) { <a [routerLink]="['/projects', project.key, 'tasks']" routerLinkActive="active" (click)="closeDrawer()">Tasks</a> } @else { <span aria-disabled="true" title="Tasks are disabled">Tasks</span> }@if (project.notes_enabled) { <a [routerLink]="['/projects', project.key, 'notes']" routerLinkActive="active" (click)="closeDrawer()">Notes</a> } @else { <span aria-disabled="true" title="Notes are disabled">Notes</span> }</div></article>
        }
      </section>
      <nav class="utility-nav"><span>{{ auth.user()?.display_name }}</span>@if (auth.user()?.is_admin) { <label class="toggle"><input type="checkbox" [checked]="inspection.active()" (change)="inspection.toggle($any($event.target).checked)"> Inspection</label> }<a routerLink="/account" routerLinkActive="active" (click)="closeDrawer()">Account</a>@if (auth.user()?.is_admin) { <a routerLink="/admin" routerLinkActive="active" (click)="closeDrawer()">Admin</a> }<button class="quiet" (click)="logout()">Logout</button></nav>
    </aside>
  `,
})
export class HeaderComponent implements OnDestroy {
  private media = typeof window === 'undefined' || typeof window.matchMedia !== 'function' ? undefined : window.matchMedia('(min-width: 701px)'); readonly drawer = signal(this.media?.matches ?? false);
  readonly auth = inject(AuthService); readonly inspection = inject(InspectionService); private api = inject(ApiService); private router = inject(Router); readonly projects = signal<Project[]>([]);
  private onMediaChange = (event: MediaQueryListEvent) => this.drawer.set(event.matches);
  constructor() { this.media?.addEventListener('change', this.onMediaChange); void this.loadProjects(); }
  async loadProjects() { try { this.projects.set(await this.api.request<Project[]>('/api/projects?inspection=false&include_archived=false')); } catch { /* Global navigation remains available. */ } }
  titleColor(color?: string | null) { if (!color || !/^#[0-9a-f]{6}$/i.test(color)) return '#403d37'; const linear = (channel: number) => channel <= .04045 ? channel / 12.92 : ((channel + .055) / 1.055) ** 2.4, luminance = (channels: number[]) => channels.map(linear).reduce((sum, channel, index) => sum + channel * [.2126, .7152, .0722][index], 0), foregroundLuminance = luminance([1, 3, 5].map(i => parseInt(color.slice(i, i + 2), 16) / 255)), sidebarLuminance = luminance([255, 253, 250].map(channel => channel / 255)); return (sidebarLuminance + .05) / (foregroundLuminance + .05) >= 4.5 ? color : '#403d37'; }
  toggleDrawer() { this.drawer.update(open => !open); } closeDrawer() { if (!this.media?.matches) this.drawer.set(false); } ngOnDestroy() { this.media?.removeEventListener('change', this.onMediaChange); }
  async logout() { await this.auth.logout(); await this.router.navigateByUrl('/login'); }
}
