import { Component, inject, signal } from '@angular/core';
import { NgIf } from '@angular/common';
import { ReactiveFormsModule, FormControl, FormGroup, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { AuthService } from '../core/auth.service';

@Component({ imports: [NgIf, ReactiveFormsModule], template: `<main class="login"><h1>Change temporary password</h1><form [formGroup]="form" (ngSubmit)="change()"><label>Temporary password<input formControlName="current" type="password" required></label><label>New password<input formControlName="password" type="password" minlength="12" required></label><button>Change password</button></form><p class="error" *ngIf="error()">{{ error() }}</p></main>` })
export class PasswordChangeComponent {
  private auth = inject(AuthService); private router = inject(Router); private route = inject(ActivatedRoute); readonly error = signal('');
  readonly form = new FormGroup({ current: new FormControl('', { nonNullable: true, validators: Validators.required }), password: new FormControl('', { nonNullable: true, validators: [Validators.required, Validators.minLength(12)] }) });
  private returnUrl() { const url = this.route.snapshot.queryParamMap.get('returnUrl'); return url && /^\/(?!\/)(?![^/?#]*:)/.test(url) && !/^\/(?:login|password-change)(?:[/?#]|$)/.test(url) ? url : '/projects'; }
  async change() { if (this.form.invalid) return; try { await this.auth.changePassword(this.form.value.current!, this.form.value.password!); this.error.set('Password changed. Sign in again.'); await this.router.navigateByUrl(`/login?returnUrl=${encodeURIComponent(this.returnUrl())}`); } catch (error) { this.error.set(error instanceof Error ? error.message : String(error)); } }
}
