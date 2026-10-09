/**
 * Schedules — Create and manage recurring report tickets.
 *
 * Layout:
 *   Left panel  — schedule list with status, next run, pause/resume/fire controls
 *   Right panel — create/edit form (slides in when "New schedule" or "Edit" clicked)
 */
import { useEffect, useState, useCallback } from 'react';
import {
  Alert, Box, Button, Chip, CircularProgress,
  Dialog, DialogActions, DialogContent, DialogTitle,
  Divider, FormControl, FormHelperText, IconButton,
  InputLabel, MenuItem, Paper, Select, Stack,
  Table, TableBody, TableCell, TableHead, TableRow,
  TextField, Tooltip, Typography,
} from '@mui/material';
import {
  AddOutlined, DeleteOutlined, EditOutlined,
  PauseOutlined, PlayArrowOutlined, FlashOnOutlined,
  RepeatOutlined, OpenInNewOutlined,
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { schedulesAPI, type Schedule, type ScheduleCreate } from '../../api/schedules';
import { requestsAPI } from '../../api/requests';
import { usersAPI } from '../../api/users';

// ── helpers ───────────────────────────────────────────────────────────────────

const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
const PRIORITY_COLOUR: Record<string, 'default' | 'info' | 'warning' | 'error'> = {
  low: 'default', medium: 'info', high: 'warning', urgent: 'error',
};

function humanSchedule(s: Schedule): string {
  const time = `${String(s.hour).padStart(2, '0')}:${String(s.minute).padStart(2, '0')}`;
  if (s.frequency === 'daily')    return `Every day at ${time}`;
  if (s.frequency === 'weekly')   return `Every ${DAYS[s.day_of_week ?? 0]} at ${time}`;
  if (s.frequency === 'biweekly') return `Every 2 weeks (${DAYS[s.day_of_week ?? 0]}) at ${time}`;
  if (s.frequency === 'monthly')  return `Monthly on day ${s.day_of_month} at ${time}`;
  return s.frequency;
}

function NextRunBadge({ schedule }: { schedule: Schedule }) {
  if (!schedule.is_active) return <Chip label="Paused" size="small" color="default" />;
  if (!schedule.next_run_at) return <Chip label="Pending" size="small" color="default" />;
  const next = new Date(schedule.next_run_at);
  const now  = Date.now();
  const hrs  = (next.getTime() - now) / 3600000;
  const label = hrs < 0
    ? 'Overdue'
    : hrs < 1
    ? `${Math.round(hrs * 60)}m`
    : hrs < 24
    ? `${Math.round(hrs)}h`
    : next.toLocaleDateString();
  return (
    <Tooltip title={`Next: ${next.toLocaleString()}`}>
      <Chip
        label={label}
        size="small"
        color={hrs < 0 ? 'error' : hrs < 2 ? 'warning' : 'success'}
        variant="outlined"
        sx={{ fontWeight: 700, fontSize: 11 }}
      />
    </Tooltip>
  );
}

// ── blank form ────────────────────────────────────────────────────────────────

const BLANK: ScheduleCreate = {
  title:           '',
  description:     '',
  request_type_id: 0,
  priority:        'medium',
  due_in_hours:    24,
  preferred_officer_id: null,
  completion_mode: 'require_feedback',
  frequency:       'weekly',
  hour:            9,
  minute:          0,
  day_of_week:     0,
  day_of_month:    1,
};

// ── main component ────────────────────────────────────────────────────────────

export function Schedules() {
  const [schedules,   setSchedules]   = useState<Schedule[]>([]);
  const [loading,     setLoading]     = useState(true);
  const [error,       setError]       = useState('');
  const [success,     setSuccess]     = useState('');
  const [firedTicketId, setFiredTicketId] = useState<number | null>(null);

  const navigate = useNavigate();

  // form state
  const [formOpen,    setFormOpen]    = useState(false);
  const [editId,      setEditId]      = useState<number | null>(null);
  const [form,        setForm]        = useState<ScheduleCreate>({ ...BLANK });
  const [saving,      setSaving]      = useState(false);
  const [formError,   setFormError]   = useState('');

  // delete confirm
  const [deleteTarget, setDeleteTarget] = useState<Schedule | null>(null);
  const [deleting,     setDeleting]     = useState(false);

  // lookup data
  const [reqTypes,    setReqTypes]    = useState<{ id: number; name: string }[]>([]);
  const [officers,    setOfficers]    = useState<{ id: number; full_name: string | null; email: string }[]>([]);

  // ── load ────────────────────────────────────────────────────────────────────
  const reload = useCallback(() => {
    setLoading(true);
    schedulesAPI.list()
      .then((r) => setSchedules(r.data))
      .catch(() => setError('Unable to load schedules'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    reload();
    requestsAPI.listTypes().then((r) => setReqTypes(r.data)).catch(() => undefined);
    usersAPI.misTeam().then((r) => setOfficers(r.data)).catch(() => undefined);
  }, [reload]);

  // ── form helpers ─────────────────────────────────────────────────────────────
  const openCreate = () => {
    setEditId(null);
    setForm({ ...BLANK, request_type_id: reqTypes[0]?.id ?? 0 });
    setFormError('');
    setFormOpen(true);
  };

  const openEdit = (s: Schedule) => {
    setEditId(s.id);
    setForm({
      title:                s.title,
      description:          s.description ?? '',
      request_type_id:      s.request_type_id,
      priority:             s.priority,
      due_in_hours:         s.due_in_hours,
      preferred_officer_id: s.preferred_officer_id,
      completion_mode:      s.completion_mode,
      frequency:            s.frequency,
      hour:                 s.hour,
      minute:               s.minute,
      day_of_week:          s.day_of_week,
      day_of_month:         s.day_of_month,
    });
    setFormError('');
    setFormOpen(true);
  };

  const f = (field: keyof ScheduleCreate, value: unknown) =>
    setForm((prev) => ({ ...prev, [field]: value }));

  const saveSchedule = async () => {
    if (!form.title.trim())         { setFormError('Title is required'); return; }
    if (!form.request_type_id)      { setFormError('Report type is required'); return; }
    if (form.frequency === 'monthly' && !form.day_of_month) {
      setFormError('Day of month is required for monthly schedules'); return;
    }
    setSaving(true);
    setFormError('');
    try {
      const payload = {
        ...form,
        description:          form.description || undefined,
        preferred_officer_id: form.preferred_officer_id || undefined,
        day_of_week:          ['weekly','biweekly'].includes(form.frequency) ? form.day_of_week : undefined,
        day_of_month:         form.frequency === 'monthly' ? form.day_of_month : undefined,
      };
      if (editId) {
        await schedulesAPI.update(editId, payload);
        setSuccess('Schedule updated.');
      } else {
        await schedulesAPI.create(payload as ScheduleCreate);
        setSuccess('Schedule created — first ticket will fire at the scheduled time.');
      }
      setFormOpen(false);
      reload();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } }).response?.data?.detail;
      setFormError(typeof detail === 'string' ? detail : 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  // ── actions ──────────────────────────────────────────────────────────────────
  const toggle = async (s: Schedule) => {
    try {
      const updated = s.is_active
        ? await schedulesAPI.pause(s.id)
        : await schedulesAPI.resume(s.id);
      setSchedules((prev) => prev.map((x) => x.id === s.id ? updated.data : x));
      setSuccess(s.is_active ? `"${s.title}" paused.` : `"${s.title}" resumed.`);
    } catch {
      setError('Action failed');
    }
  };

  const fireNow = async (s: Schedule) => {
    try {
      const res = await schedulesAPI.fireNow(s.id);
      setFiredTicketId(res.data.ticket_id);
      setSuccess(`Ticket #${String(res.data.ticket_id).padStart(5, '0')} created from "${s.title}". Click to open it.`);
      reload();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } }).response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Fire failed');
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await schedulesAPI.delete(deleteTarget.id);
      setSuccess(`"${deleteTarget.title}" deleted.`);
      setDeleteTarget(null);
      reload();
    } catch {
      setError('Delete failed');
    } finally {
      setDeleting(false);
    }
  };

  // ── render ────────────────────────────────────────────────────────────────────
  return (
    <Stack spacing={3}>
      {/* header */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 2 }}>
        <Box>
          <Typography variant="h5" fontWeight={700}>Recurring Schedules</Typography>
          <Typography variant="body2" color="text.secondary">
            Automate repetitive report requests — tickets are created and assigned automatically.
          </Typography>
        </Box>
        <Button
          variant="contained"
          startIcon={<AddOutlined />}
          onClick={openCreate}
          sx={{ bgcolor: '#7B1235', '&:hover': { bgcolor: '#5f0d29' } }}
        >
          New schedule
        </Button>
      </Box>

      {error   && <Alert severity="error"   onClose={() => setError('')}>{error}</Alert>}
      {success && (
        <Alert
          severity="success"
          onClose={() => { setSuccess(''); setFiredTicketId(null); }}
          action={
            firedTicketId ? (
              <Button
                size="small"
                color="inherit"
                startIcon={<OpenInNewOutlined fontSize="small" />}
                onClick={() => navigate(`/requests/${firedTicketId}`)}
              >
                View ticket
              </Button>
            ) : undefined
          }
        >
          {success}
        </Alert>
      )}

      {/* schedule table */}
      <Paper>
        {loading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', p: 6 }}>
            <CircularProgress />
          </Box>
        ) : schedules.length === 0 ? (
          <Box sx={{ p: 6, textAlign: 'center' }}>
            <RepeatOutlined sx={{ fontSize: 48, color: '#ccc', mb: 2 }} />
            <Typography color="text.secondary" fontWeight={600}>No schedules yet</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: .5 }}>
              Create a schedule to automate recurring report requests.
            </Typography>
            <Button
              variant="contained" sx={{ mt: 2, bgcolor: '#7B1235', '&:hover': { bgcolor: '#5f0d29' } }}
              startIcon={<AddOutlined />} onClick={openCreate}
            >
              Create first schedule
            </Button>
          </Box>
        ) : (
          <Table size="small">
            <TableHead>
              <TableRow sx={{ '& th': { fontWeight: 700, fontSize: 12, color: '#5a4a50', bgcolor: '#faf7f5', letterSpacing: .4 } }}>
                <TableCell sx={{ pl: 2.5 }}>Schedule</TableCell>
                <TableCell>Frequency</TableCell>
                <TableCell>Priority</TableCell>
                <TableCell>Auto-assign</TableCell>
                <TableCell>Completion</TableCell>
                <TableCell>Next run</TableCell>
                <TableCell align="center">Fired</TableCell>
                <TableCell align="right" sx={{ pr: 2 }}>Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {schedules.map((s) => (
                <TableRow
                  key={s.id}
                  hover
                  sx={{
                    '&:last-child td': { border: 0 },
                    opacity: s.is_active ? 1 : 0.55,
                  }}
                >
                  <TableCell sx={{ pl: 2.5, py: 1.5 }}>
                    <Typography variant="body2" fontWeight={600}>{s.title}</Typography>
                    <Typography variant="caption" color="text.secondary">
                      {s.request_type_name} · {s.owner_name}
                    </Typography>
                  </TableCell>

                  <TableCell>
                    <Typography variant="body2">{humanSchedule(s)}</Typography>
                  </TableCell>

                  <TableCell>
                    <Chip
                      size="small"
                      label={s.priority}
                      color={PRIORITY_COLOUR[s.priority] ?? 'default'}
                      variant="outlined"
                      sx={{ fontWeight: 600, fontSize: 11, textTransform: 'capitalize' }}
                    />
                  </TableCell>

                  <TableCell>
                    <Typography variant="body2" color={s.preferred_officer_name ? 'text.primary' : 'text.secondary'}>
                      {s.preferred_officer_name ?? '—'}
                    </Typography>
                  </TableCell>

                  <TableCell>
                    <Chip
                      size="small"
                      label={s.completion_mode === 'auto_close' ? 'Auto-close' : 'Needs feedback'}
                      color={s.completion_mode === 'auto_close' ? 'success' : 'default'}
                      variant="outlined"
                      sx={{ fontSize: 11 }}
                    />
                  </TableCell>

                  <TableCell><NextRunBadge schedule={s} /></TableCell>

                  <TableCell align="center">
                    <Typography variant="body2" fontWeight={700}>{s.total_fired}</Typography>
                  </TableCell>

                  <TableCell align="right" sx={{ pr: 1.5 }}>
                    <Stack direction="row" spacing={0.5} justifyContent="flex-end">
                      {/* Pause / Resume */}
                      <Tooltip title={s.is_active ? 'Pause' : 'Resume'}>
                        <IconButton size="small" onClick={() => toggle(s)}>
                          {s.is_active
                            ? <PauseOutlined fontSize="small" />
                            : <PlayArrowOutlined fontSize="small" sx={{ color: '#2e6b57' }} />}
                        </IconButton>
                      </Tooltip>

                      {/* Fire now */}
                      <Tooltip title="Fire now — create ticket immediately">
                        <IconButton size="small" onClick={() => fireNow(s)} sx={{ color: '#7B1235' }}>
                          <FlashOnOutlined fontSize="small" />
                        </IconButton>
                      </Tooltip>

                      {/* Edit */}
                      <Tooltip title="Edit">
                        <IconButton size="small" onClick={() => openEdit(s)}>
                          <EditOutlined fontSize="small" />
                        </IconButton>
                      </Tooltip>

                      {/* Delete */}
                      <Tooltip title="Delete">
                        <IconButton size="small" onClick={() => setDeleteTarget(s)} sx={{ color: '#c62828' }}>
                          <DeleteOutlined fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    </Stack>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Paper>

      {/* ── Create / Edit dialog ── */}
      <Dialog open={formOpen} onClose={() => setFormOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editId ? 'Edit schedule' : 'New recurring schedule'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2.5} sx={{ pt: 1 }}>

            {formError && <Alert severity="error">{formError}</Alert>}

            {/* Title */}
            <TextField
              label="Title"
              value={form.title}
              onChange={(e) => f('title', e.target.value)}
              required
              placeholder="e.g. Weekly Branch Summary"
              helperText="This becomes the ticket title each time it fires"
            />

            {/* Description */}
            <TextField
              label="Description / instructions"
              value={form.description}
              onChange={(e) => f('description', e.target.value)}
              multiline minRows={2}
              placeholder="Any standing instructions for the MIS team…"
            />

            <Divider />

            {/* Report type + Priority side by side */}
            <Box sx={{ display: 'flex', gap: 2 }}>
              <FormControl sx={{ flex: 2 }} required>
                <InputLabel>Report type</InputLabel>
                <Select
                  label="Report type"
                  value={form.request_type_id || ''}
                  onChange={(e) => f('request_type_id', Number(e.target.value))}
                >
                  {reqTypes.map((rt) => (
                    <MenuItem key={rt.id} value={rt.id}>{rt.name}</MenuItem>
                  ))}
                </Select>
              </FormControl>

              <FormControl sx={{ flex: 1 }}>
                <InputLabel>Priority</InputLabel>
                <Select label="Priority" value={form.priority} onChange={(e) => f('priority', e.target.value)}>
                  {['low','medium','high','urgent'].map((p) => (
                    <MenuItem key={p} value={p} sx={{ textTransform: 'capitalize' }}>{p}</MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Box>

            {/* Due in hours */}
            <TextField
              label="Due date offset (hours)"
              type="number"
              value={form.due_in_hours}
              onChange={(e) => f('due_in_hours', Number(e.target.value))}
              helperText="Each generated ticket's due date = creation time + this many hours"
              slotProps={{ htmlInput: { min: 1, max: 720 } }}
            />

            <Divider />

            {/* Frequency */}
            <FormControl required>
              <InputLabel>Frequency</InputLabel>
              <Select label="Frequency" value={form.frequency} onChange={(e) => f('frequency', e.target.value)}>
                <MenuItem value="daily">Daily</MenuItem>
                <MenuItem value="weekly">Weekly</MenuItem>
                <MenuItem value="biweekly">Every two weeks</MenuItem>
                <MenuItem value="monthly">Monthly</MenuItem>
              </Select>
              <FormHelperText>How often a new ticket should be created</FormHelperText>
            </FormControl>

            {/* Day of week — shown for weekly / biweekly */}
            {(form.frequency === 'weekly' || form.frequency === 'biweekly') && (
              <FormControl>
                <InputLabel>Day of week</InputLabel>
                <Select
                  label="Day of week"
                  value={form.day_of_week ?? 0}
                  onChange={(e) => f('day_of_week', Number(e.target.value))}
                >
                  {DAYS.map((d, i) => <MenuItem key={i} value={i}>{d}</MenuItem>)}
                </Select>
              </FormControl>
            )}

            {/* Day of month — shown for monthly */}
            {form.frequency === 'monthly' && (
              <TextField
                label="Day of month"
                type="number"
                value={form.day_of_month ?? 1}
                onChange={(e) => f('day_of_month', Number(e.target.value))}
                helperText="1–28 (use 28 to always hit the last safe day)"
                slotProps={{ htmlInput: { min: 1, max: 28 } }}
              />
            )}

            {/* Time */}
            <Box sx={{ display: 'flex', gap: 2 }}>
              <TextField
                label="Hour (0–23)"
                type="number"
                value={form.hour}
                onChange={(e) => f('hour', Number(e.target.value))}
                sx={{ flex: 1 }}
                slotProps={{ htmlInput: { min: 0, max: 23 } }}
              />
              <TextField
                label="Minute (0–59)"
                type="number"
                value={form.minute}
                onChange={(e) => f('minute', Number(e.target.value))}
                sx={{ flex: 1 }}
                slotProps={{ htmlInput: { min: 0, max: 59 } }}
              />
            </Box>

            <Divider />

            {/* Preferred MIS Officer */}
            <FormControl>
              <InputLabel>Preferred MIS Officer (optional)</InputLabel>
              <Select
                label="Preferred MIS Officer (optional)"
                value={form.preferred_officer_id ?? ''}
                onChange={(e) => f('preferred_officer_id', e.target.value === '' ? null : Number(e.target.value))}
              >
                <MenuItem value="">None — let MIS Manager assign</MenuItem>
                {officers.map((u) => (
                  <MenuItem key={u.id} value={u.id}>
                    {u.full_name || u.email}
                  </MenuItem>
                ))}
              </Select>
              <FormHelperText>
                If set, the ticket skips dept-approval and is assigned directly to this officer
              </FormHelperText>
            </FormControl>

            {/* Completion mode */}
            <FormControl>
              <InputLabel>Completion mode</InputLabel>
              <Select
                label="Completion mode"
                value={form.completion_mode}
                onChange={(e) => f('completion_mode', e.target.value)}
              >
                <MenuItem value="require_feedback">
                  Require feedback — requester rates the report before ticket closes
                </MenuItem>
                <MenuItem value="auto_close">
                  Auto-close — ticket closes automatically when MIS marks it resolved
                </MenuItem>
              </Select>
            </FormControl>

          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setFormOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={saveSchedule}
            disabled={saving}
            sx={{ bgcolor: '#7B1235', '&:hover': { bgcolor: '#5f0d29' } }}
          >
            {saving ? 'Saving…' : editId ? 'Save changes' : 'Create schedule'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* ── Delete confirm dialog ── */}
      <Dialog open={!!deleteTarget} onClose={() => setDeleteTarget(null)} maxWidth="xs" fullWidth>
        <DialogTitle>Delete schedule?</DialogTitle>
        <DialogContent>
          <Typography>
            Are you sure you want to delete <strong>"{deleteTarget?.title}"</strong>?
            This will not affect tickets already created by this schedule.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteTarget(null)}>Cancel</Button>
          <Button
            variant="contained" color="error"
            onClick={confirmDelete} disabled={deleting}
          >
            {deleting ? 'Deleting…' : 'Delete'}
          </Button>
        </DialogActions>
      </Dialog>

    </Stack>
  );
}
