import type { components } from '@event-ticketing/shared-ui/esb-contract';

export type Role = components['schemas']['AuthRole'];
export type User = components['schemas']['User'];
export type TokenResponse = components['schemas']['TokenResponse'];

export type AuthSession = {
  accessToken: string;
  expiresIn: number;
  user: User;
};
