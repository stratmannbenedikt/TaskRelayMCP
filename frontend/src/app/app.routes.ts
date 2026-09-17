import { Routes, CanActivateFn, CanDeactivateFn, Router, RouterStateSnapshot } from '@angular/router';
import { inject } from '@angular/core';
import { AuthService } from './core/auth.service';
import { LoginComponent } from './pages/login.component';
import { PasswordChangeComponent } from './pages/password-change.component';
import { ProjectsComponent } from './pages/projects.component';
import { ProjectComponent } from './pages/project.component';
import { AccountComponent } from './pages/account.component';
import { AdminComponent } from './pages/admin.component';
import { ProjectSettingsComponent } from './pages/project-settings.component';
import { ProjectLandingComponent } from './pages/project-landing.component';
import { NotesComponent } from './pages/notes.component';
import { GlobalTasksComponent } from './pages/global-tasks.component';
import { GlobalNotesComponent } from './pages/global-notes.component';
import { TagManagementComponent } from './pages/tag-management.component';

const safeReturnUrl = (url: string) => /^\/(?!\/)(?![^/?#]*:)/.test(url) && !/^\/(?:login|password-change)(?:[/?#]|$)/.test(url) ? url : '/home';
export const readyGuard: CanActivateFn = (_route, state: RouterStateSnapshot) => { const auth = inject(AuthService), router = inject(Router), returnUrl = safeReturnUrl(state.url), check = () => { const user = auth.user(); return user && !user.must_change_password ? true : router.createUrlTree([user ? '/password-change' : '/login'], { queryParams: { returnUrl } }); }; return auth.user() === undefined ? auth.load().then(check) : check(); };
export const adminGuard: CanActivateFn = () => inject(AuthService).user()?.is_admin ? true : inject(Router).createUrlTree(['/home']);
export const noteUnsavedGuard: CanDeactivateFn<NotesComponent> = component => component.canDeactivate();
export const taskUnsavedGuard: CanDeactivateFn<ProjectComponent> = component => component.canDeactivate();
export const routes: Routes = [
  { path: 'login', component: LoginComponent }, { path: 'password-change', component: PasswordChangeComponent },
  { path: 'home', component: ProjectsComponent, canActivate: [readyGuard] },
  { path: 'tasks', component: GlobalTasksComponent, canActivate: [readyGuard] },
  { path: 'notes/:noteId', component: GlobalNotesComponent, canActivate: [readyGuard] }, { path: 'notes', component: GlobalNotesComponent, canActivate: [readyGuard] },
  { path: 'projects', pathMatch: 'full', redirectTo: 'home' },
  { path: 'projects/:key/tasks/:taskId', component: ProjectComponent, canActivate: [readyGuard], canDeactivate: [taskUnsavedGuard] }, { path: 'projects/:key/tasks', component: ProjectComponent, canActivate: [readyGuard], canDeactivate: [taskUnsavedGuard] }, { path: 'projects/:key/tags', component: TagManagementComponent, canActivate: [readyGuard] }, { path: 'projects/:key/notes/new', component: NotesComponent, canActivate: [readyGuard], canDeactivate: [noteUnsavedGuard], data: { draft: true } }, { path: 'projects/:key/notes/:noteId', component: NotesComponent, canActivate: [readyGuard], canDeactivate: [noteUnsavedGuard] }, { path: 'projects/:key/notes', component: NotesComponent, canActivate: [readyGuard] }, { path: 'projects/:key/settings', component: ProjectSettingsComponent, canActivate: [readyGuard] },
  { path: 'projects/:key', pathMatch: 'full', component: ProjectLandingComponent, canActivate: [readyGuard] },
  { path: 'account', component: AccountComponent, canActivate: [readyGuard] }, { path: 'admin', component: AdminComponent, canActivate: [readyGuard, adminGuard] },
  { path: '', pathMatch: 'full', redirectTo: 'home' }, { path: '**', redirectTo: 'home' }
];
