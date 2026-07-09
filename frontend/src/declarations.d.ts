/** Build identity, set on process.env by vite.config.ts (dev + build). */
interface ImportMetaEnv {
  readonly VITE_APP_VERSION: string
  readonly VITE_BUILD_TIME: string
  readonly VITE_CLERK_PUBLISHABLE_KEY: string
}
interface ImportMeta {
  readonly env: ImportMetaEnv
}

declare module 'reactjs-social-login' {
  import React from 'react'

  export interface IResolveParams {
    provider: string
    data?: Record<string, unknown>
  }

  export interface LoginSocialGoogleProps {
    client_id: string
    scope?: string
    onResolve: (params: IResolveParams) => void
    onReject: (err: unknown) => void
    children: React.ReactNode
    [key: string]: unknown
  }

  export interface LoginSocialMicrosoftProps {
    client_id: string
    redirect_uri?: string
    scope?: string
    onResolve: (params: IResolveParams) => void
    onReject: (err: unknown) => void
    children: React.ReactNode
    [key: string]: unknown
  }

  export const LoginSocialGoogle: React.FC<LoginSocialGoogleProps>
  export const LoginSocialMicrosoft: React.FC<LoginSocialMicrosoftProps>
}
