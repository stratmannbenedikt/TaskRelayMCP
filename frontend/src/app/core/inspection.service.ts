import { Injectable, signal } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class InspectionService { readonly active = signal(false); toggle(active: boolean) { this.active.set(active); } }
