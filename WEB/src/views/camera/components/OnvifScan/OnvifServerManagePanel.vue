<template>
  <div>
    <a-alert
      type="info"
      show-icon
      message="列出当前库中设备 IP（去重），且不在全局 IP 黑名单中的地址。可将不需要扫描的 IP 批量加入黑名单以加速扫描。"
      class="mb-3"
    />
    <BasicTable @register="registerTable">
      <template #toolbar>
        <div class="flex flex-col gap-2 w-full max-w-2xl">
          <a-textarea
            v-model:value="batchText"
            :rows="3"
            placeholder="批量输入 IP，每行一个或逗号分隔"
          />
          <div class="flex gap-2 flex-wrap">
            <a-input v-model:value="batchNote" placeholder="备注（可选）" style="max-width: 280px" />
            <a-button type="primary" :loading="batchLoading" @click="submitBatchRaw">
              批量加入黑名单
            </a-button>
          </div>
        </div>
      </template>
      <template #bodyCell="{ column, record }">
        <template v-if="column.dataIndex === 'action'">
          <a-button type="link" size="small" @click="addOne(record.ip)">加入黑名单</a-button>
        </template>
      </template>
    </BasicTable>
  </div>
</template>

<script lang="ts" setup>
import { ref } from 'vue';
import { BasicTable, useTable } from '@/components/Table';
import { useMessage } from '@/hooks/web/useMessage';
import type { BasicColumn } from '@/components/Table';
import { batchAddIpBlacklist, listServerCandidates } from '@/api/device/onvif_scan';

const { createMessage } = useMessage();

const batchText = ref('');
const batchNote = ref('');
const batchLoading = ref(false);

const columns: BasicColumn[] = [
  { title: 'IP', dataIndex: 'ip', width: 160 },
  { title: '关联设备数', dataIndex: 'device_count', width: 100 },
  { title: '示例名称', dataIndex: 'sample_name', width: 160 },
  { title: '操作', dataIndex: 'action', width: 120 },
];

async function fetchList(params: Record<string, any>) {
  const res: any = await listServerCandidates({
    pageNo: params.page,
    pageSize: params.pageSize,
  });
  return { list: res.data ?? [], total: res.total ?? 0 };
}

const [registerTable, { reload }] = useTable({
  title: '服务器（候选 IP）',
  api: fetchList,
  columns,
  pagination: true,
  rowKey: 'ip',
});

async function addOne(ip: string) {
  try {
    const r: any = await batchAddIpBlacklist({ ips: [ip], note: batchNote.value });
    const added = r?.added ?? r?.data?.added;
    createMessage.success(`已加入黑名单${added != null ? `（${added}）` : ''}`);
    reload();
  } catch (e) {
    console.error(e);
  }
}

async function submitBatchRaw() {
  const raw = batchText.value?.trim();
  if (!raw) {
    createMessage.warning('请输入 IP');
    return;
  }
  batchLoading.value = true;
  try {
    const r: any = await batchAddIpBlacklist({ raw, note: batchNote.value });
    const result = r?.data ?? r;
    createMessage.success(
      `完成：新增 ${result.added ?? 0}，跳过 ${result.skipped ?? 0}（无效或已存在）`,
    );
    batchText.value = '';
    reload();
  } catch (e) {
    console.error(e);
  } finally {
    batchLoading.value = false;
  }
}
</script>
