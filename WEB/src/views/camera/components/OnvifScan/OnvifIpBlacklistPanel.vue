<template>
  <div>
    <a-alert
      type="warning"
      show-icon
      message="黑名单中的 IP 将跳过 ONVIF 扫描（不探测、不注册、不更新）。移出后可再次被扫描。"
      class="mb-3"
    />
    <BasicTable @register="registerTable">
      <template #bodyCell="{ column, record }">
        <template v-if="column.dataIndex === 'action'">
          <TableAction
            :actions="[
              {
                label: '移出黑名单',
                color: 'error',
                popConfirm: {
                  title: '确认移出？移出后下一轮扫描可能再次发现该 IP。',
                  confirm: () => handleRemove(record),
                },
              },
            ]"
          />
        </template>
      </template>
    </BasicTable>
  </div>
</template>

<script lang="ts" setup>
import { BasicTable, TableAction, useTable } from '@/components/Table';
import { useMessage } from '@/hooks/web/useMessage';
import type { BasicColumn } from '@/components/Table';
import { listIpBlacklist, removeIpBlacklist } from '@/api/device/onvif_scan';

const { createMessage } = useMessage();

const columns: BasicColumn[] = [
  { title: 'ID', dataIndex: 'id', width: 70 },
  { title: 'IP', dataIndex: 'ip', width: 160 },
  { title: '备注', dataIndex: 'note', width: 200 },
  { title: '创建时间', dataIndex: 'created_at', width: 180 },
  { title: '操作', dataIndex: 'action', width: 140 },
];

async function fetchList(params: Record<string, any>) {
  const res: any = await listIpBlacklist({
    pageNo: params.page,
    pageSize: params.pageSize,
  });
  return { list: res.data ?? [], total: res.total ?? 0 };
}

const [registerTable, { reload }] = useTable({
  title: 'IP 黑名单',
  api: fetchList,
  columns,
  pagination: true,
  rowKey: 'id',
});

async function handleRemove(record: any) {
  try {
    await removeIpBlacklist(record.id);
    createMessage.success('已移出黑名单');
    reload();
  } catch (e) {
    console.error(e);
  }
}
</script>
