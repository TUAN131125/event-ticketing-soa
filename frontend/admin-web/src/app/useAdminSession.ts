import { useOutletContext } from 'react-router-dom';

type AdminOutletContext = { accessToken: string };

export function useAdminSession(): AdminOutletContext {
  return useOutletContext<AdminOutletContext>();
}
