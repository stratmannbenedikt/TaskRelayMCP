import { Component, inject } from '@angular/core';
import { NgIf } from '@angular/common';
import { RouterOutlet } from '@angular/router';
import { AuthService } from './core/auth.service';

@Component({ selector: 'app-root', imports: [NgIf, RouterOutlet], template: '<main *ngIf="auth.user() === undefined"><p>Loading…</p></main><router-outlet *ngIf="auth.user() !== undefined" />' })
export class AppComponent { readonly auth = inject(AuthService); constructor() { void this.auth.load(); } }
