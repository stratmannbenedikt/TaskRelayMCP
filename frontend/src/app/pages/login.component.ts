import { Component, inject, signal } from '@angular/core';
import { NgIf } from '@angular/common';
import { ReactiveFormsModule, FormControl, FormGroup, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { AuthService } from '../core/auth.service';

@Component({ imports: [NgIf, ReactiveFormsModule], template: `<main class="login"><h1>Task<strong>Relay</strong></h1><form [formGroup]="form" (ngSubmit)="login()"><label>Username<input formControlName="username" autocomplete="username" required autofocus></label><label>Password<input formControlName="password" type="password" autocomplete="current-password" required></label><button>Sign in</button></form><p class="error" *ngIf="error()">{{ error() }}</p></main>` })
export class LoginComponent {
  private auth = inject(AuthService); private router = inject(Router); private route = inject(ActivatedRoute); readonly error = signal('');
  readonly form = new FormGroup({ username: new FormControl('', { nonNullable: true, validators: Validators.required }), password: new FormControl('', { nonNullable: true, validators: Validators.required }) });
  private returnUrl() { const url = this.route.snapshot.queryParamMap.get('returnUrl'); return url && /^\/(?!\/)(?![^/?#]*:)/.test(url) && !/^\/(?:login|password-change)(?:[/?#]|$)/.test(url) ? url : '/home'; }
  async login() { if (this.form.invalid) return; try { await this.auth.login(this.form.value.username!, this.form.value.password!); const returnUrl = this.returnUrl(); await this.router.navigateByUrl(this.auth.user()?.must_change_password ? `/password-change?returnUrl=${encodeURIComponent(returnUrl)}` : returnUrl); } catch (error) { this.error.set(error instanceof Error ? error.message : String(error)); } }
}
