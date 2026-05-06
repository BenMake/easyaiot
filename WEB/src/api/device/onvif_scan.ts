import { defHttp } from '@/utils/http/axios';

const PREFIX = '/video/onvif-scan';

const commonApi = <T = any>(
  method: 'get' | 'post' | 'delete' | 'put',
  url: string,
  data?: any,
  headers = {},
  isTransformResponse = true,
) => {
  defHttp.setHeader({ 'X-Authorization': 'Bearer ' + localStorage.getItem('jwt_token') });
  return defHttp[method]<T>(
    {
      url,
      headers: { ...headers },
      ...(method === 'get' ? { params: data } : { data }),
    },
    { isTransformResponse },
  );
};

export const listOnvifPasswordLibraries = (params?: { pageNo?: number; pageSize?: number }) =>
  commonApi('get', `${PREFIX}/password-library/list`, params);

export const getOnvifPasswordLibrary = (id: number, withSecrets = false) =>
  commonApi('get', `${PREFIX}/password-library/${id}`, { with_secrets: withSecrets ? 1 : 0 });

export const createOnvifPasswordLibrary = (data: {
  name: string;
  lib_code: string;
  credentials: { username: string; password: string }[];
  description?: string;
}) => commonApi('post', `${PREFIX}/password-library`, data);

export const updateOnvifPasswordLibrary = (
  id: number,
  data: { name?: string; description?: string; credentials?: { username: string; password: string }[] },
) => commonApi('put', `${PREFIX}/password-library/${id}`, data);

export const deleteOnvifPasswordLibrary = (id: number) =>
  commonApi('delete', `${PREFIX}/password-library/${id}`);

export const listOnvifScanTasks = (params?: { pageNo?: number; pageSize?: number }) =>
  commonApi('get', `${PREFIX}/task/list`, params);

export const getOnvifScanTask = (id: number) => commonApi('get', `${PREFIX}/task/${id}`);

export const createOnvifScanTask = (data: Record<string, any>) =>
  commonApi('post', `${PREFIX}/task`, data);

export const updateOnvifScanTask = (id: number, data: Record<string, any>) =>
  commonApi('put', `${PREFIX}/task/${id}`, data);

export const deleteOnvifScanTask = (id: number) => commonApi('delete', `${PREFIX}/task/${id}`);

export const listOnvifSkipEntries = (
  taskId: number,
  params?: { pageNo?: number; pageSize?: number; include_released?: boolean },
) => commonApi('get', `${PREFIX}/task/${taskId}/skip/list`, params);

export const releaseOnvifSkipEntry = (entryId: number) =>
  commonApi('post', `${PREFIX}/skip/${entryId}/release`, {});

export const listIpBlacklist = (params?: { pageNo?: number; pageSize?: number }) =>
  commonApi('get', `${PREFIX}/ip-blacklist/list`, params);

export const batchAddIpBlacklist = (data: { ips?: string[]; raw?: string; note?: string }) =>
  commonApi('post', `${PREFIX}/ip-blacklist/batch`, data);

export const removeIpBlacklist = (entryId: number) =>
  commonApi('delete', `${PREFIX}/ip-blacklist/${entryId}`);

export const listServerCandidates = (params?: { pageNo?: number; pageSize?: number }) =>
  commonApi('get', `${PREFIX}/server-candidates/list`, params);
