<template>
  <div>
    <BasicTable @register="registerTable">
      <template #toolbar>
        <a-button type="primary" @click="openCreate">
          <template #icon><PlusOutlined /></template>
          新建任务
        </a-button>
      </template>
      <template #bodyCell="{ column, record }">
        <template v-if="column.dataIndex === 'is_enabled'">
          <a-tag :color="record.is_enabled ? 'green' : 'default'">
            {{ record.is_enabled ? '启用' : '停用' }}
          </a-tag>
        </template>
        <template v-else-if="column.dataIndex === 'cidrs'">
          <span :title="(record.cidrs || []).join(', ')">
            {{ (record.cidrs || []).slice(0, 2).join('，') }}{{ (record.cidrs || []).length > 2 ? '…' : '' }}
          </span>
        </template>
        <template v-else-if="column.dataIndex === 'action'">
          <TableAction
            :actions="[
              { label: '编辑', onClick: () => openEdit(record) },
              {
                label: '删除',
                color: 'error',
                popConfirm: { title: '确认删除？', confirm: () => handleDelete(record) },
              },
            ]"
          />
        </template>
      </template>
    </BasicTable>

    <a-modal
      v-model:open="modalOpen"
      :title="editingId ? '编辑扫描任务' : '新建扫描任务'"
      :width="640"
      :confirmLoading="saving"
      @ok="handleSave"
    >
      <a-form :label-col="{ span: 7 }" :wrapper-col="{ span: 16 }" class="pt-2">
        <a-form-item label="任务名称" required>
          <a-input v-model:value="form.task_name" placeholder="任务名称" />
        </a-form-item>
        <a-form-item label="任务编码" :required="!editingId">
          <a-input v-model:value="form.task_code" placeholder="留空则自动生成" :disabled="!!editingId" />
        </a-form-item>
        <a-form-item label="网段 CIDR" required>
          <a-textarea
            v-model:value="form.cidrsText"
            :rows="4"
            placeholder="每行一个，如 192.168.1.0/24"
          />
        </a-form-item>
        <a-form-item label="密码库 ID">
          <a-input-number v-model:value="form.password_library_id" :min="1" style="width: 100%" placeholder="可选" />
        </a-form-item>
        <a-form-item label="启用">
          <a-switch v-model:checked="form.is_enabled" />
        </a-form-item>
        <a-form-item label="自动注册">
          <a-switch v-model:checked="form.auto_register" />
        </a-form-item>
        <a-form-item label="指定 Worker">
          <a-input v-model:value="form.assigned_worker_id" placeholder="空=任意机器可抢" />
        </a-form-item>
        <a-form-item label="快速端口">
          <a-input v-model:value="form.portsText" placeholder="逗号分隔，默认 80,554" />
        </a-form-item>
        <a-form-item label="轮询间隔(秒)">
          <a-input-number v-model:value="form.scan_interval_sec" :min="5" style="width: 100%" />
        </a-form-item>
        <a-form-item label="每轮最大主机数">
          <a-input-number v-model:value="form.max_hosts_per_cycle" :min="1" style="width: 100%" />
        </a-form-item>
        <a-form-item label="说明">
          <a-textarea v-model:value="form.description" :rows="2" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script lang="ts" setup>
import { h, reactive, ref } from 'vue';
import { PlusOutlined } from '@ant-design/icons-vue';
import { BasicTable, TableAction, useTable } from '@/components/Table';
import { useMessage } from '@/hooks/web/useMessage';
import type { BasicColumn } from '@/components/Table';
import {
  createOnvifScanTask,
  deleteOnvifScanTask,
  listOnvifScanTasks,
  updateOnvifScanTask,
} from '@/api/device/onvif_scan';

const { createMessage } = useMessage();

const columns: BasicColumn[] = [
  { title: 'ID', dataIndex: 'id', width: 60 },
  { title: '任务名', dataIndex: 'task_name', width: 140 },
  { title: '编码', dataIndex: 'task_code', width: 120 },
  { title: '网段', dataIndex: 'cidrs', width: 200 },
  { title: '启用', dataIndex: 'is_enabled', width: 70 },
  { title: '间隔(s)', dataIndex: 'scan_interval_sec', width: 70 },
  { title: '密码库', dataIndex: 'password_library_id', width: 80 },
  { title: '操作', dataIndex: 'action', width: 120, fixed: 'right' },
];

async function fetchList(params: Record<string, any>) {
  const res: any = await listOnvifScanTasks({
    pageNo: params.page,
    pageSize: params.pageSize,
  });
  return { list: res.data ?? [], total: res.total ?? 0 };
}

const [registerTable, { reload }] = useTable({
  title: 'ONVIF 扫描任务',
  api: fetchList,
  columns,
  useSearchForm: false,
  showTableSetting: true,
  bordered: true,
  pagination: true,
  rowKey: 'id',
});

const modalOpen = ref(false);
const saving = ref(false);
const editingId = ref<number | null>(null);

const form = reactive({
  task_name: '',
  task_code: '',
  cidrsText: '',
  password_library_id: undefined as number | undefined,
  is_enabled: false,
  auto_register: true,
  assigned_worker_id: '',
  portsText: '80,554',
  scan_interval_sec: 120,
  max_hosts_per_cycle: 1024,
  description: '',
});

function resetForm() {
  form.task_name = '';
  form.task_code = '';
  form.cidrsText = '';
  form.password_library_id = undefined;
  form.is_enabled = false;
  form.auto_register = true;
  form.assigned_worker_id = '';
  form.portsText = '80,554';
  form.scan_interval_sec = 120;
  form.max_hosts_per_cycle = 1024;
  form.description = '';
}

function openCreate() {
  editingId.value = null;
  resetForm();
  modalOpen.value = true;
}

function openEdit(record: any) {
  editingId.value = record.id;
  form.task_name = record.task_name || '';
  form.task_code = record.task_code || '';
  form.cidrsText = (record.cidrs || []).join('\n');
  form.password_library_id = record.password_library_id ?? undefined;
  form.is_enabled = !!record.is_enabled;
  form.auto_register = record.auto_register !== false;
  form.assigned_worker_id = record.assigned_worker_id || '';
  form.portsText = (record.quick_scan_ports || [80, 554]).join(',');
  form.scan_interval_sec = record.scan_interval_sec ?? 120;
  form.max_hosts_per_cycle = record.max_hosts_per_cycle ?? 1024;
  form.description = record.description || '';
  modalOpen.value = true;
}

function parseCidrs(text: string): string[] {
  return text
    .split(/\r?\n/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function parsePorts(text: string): number[] {
  return text
    .split(',')
    .map((s) => parseInt(s.trim(), 10))
    .filter((n) => !Number.isNaN(n) && n > 0 && n <= 65535);
}

async function handleSave() {
  const cidrs = parseCidrs(form.cidrsText);
  if (!form.task_name.trim()) {
    createMessage.warning('请填写任务名称');
    return;
  }
  if (!cidrs.length) {
    createMessage.warning('请填写至少一个网段 CIDR');
    return;
  }
  const ports = parsePorts(form.portsText || '80,554');
  saving.value = true;
  try {
    const payload: Record<string, any> = {
      task_name: form.task_name.trim(),
      cidrs,
      is_enabled: form.is_enabled,
      auto_register: form.auto_register,
      assigned_worker_id: form.assigned_worker_id?.trim() || undefined,
      description: form.description?.trim() || undefined,
      scan_interval_sec: form.scan_interval_sec,
      max_hosts_per_cycle: form.max_hosts_per_cycle,
      quick_scan_ports: ports.length ? ports : [80, 554],
    };
    if (form.task_code?.trim()) payload.task_code = form.task_code.trim();
    if (form.password_library_id) payload.password_library_id = form.password_library_id;

    if (editingId.value) {
      await updateOnvifScanTask(editingId.value, payload);
      createMessage.success('已保存');
    } else {
      await createOnvifScanTask(payload);
      createMessage.success('已创建');
    }
    modalOpen.value = false;
    reload();
  } catch (e) {
    console.error(e);
  } finally {
    saving.value = false;
  }
}

async function handleDelete(record: any) {
  try {
    await deleteOnvifScanTask(record.id);
    createMessage.success('已删除');
    reload();
  } catch (e) {
    console.error(e);
  }
}
</script>
