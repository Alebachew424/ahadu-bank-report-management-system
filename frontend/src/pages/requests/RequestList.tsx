import { useEffect, useMemo, useState, useCallback } from 'react';
import { useLocation } from 'react-router-dom';
import {
  Alert, Box, Button, Chip, Collapse, Divider,
  InputAdornment, MenuItem, Paper,
  Stack, Table, TableBody, TableCell, TableHead,
  TableRow, TableSortLabel, TextField, Tooltip, Typography,
} from '@mui/material';
import {
  Add, FilterListOutlined, SearchOutlined,
  WarningAmberOutlined, ExpandMore, ExpandLess,
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { requestsAPI } from '../../api/requests';
import { usersAPI } from '../../api/users';
import type { ReportRequest } from '../../types/types';

const STATUS_COLOUR: Record<string, 'default' | 'warning' | 'info' | 'primary' | 'success' | 'error'> = {
  'Pending Dept Approval': 'warning',
  'Submitted':             'info',
  'Assigned':              'info',
  'In Progress':           'primary',
  'Needs Clarification':   'warning',
  'Resolved':              'success',
  'Closed':                'success',
  'Rejected':              'error',
  'Cancelled':             'error',
};

const PRIORITY_COLOUR: Record<string, 'default' | 'warning' | 'error' | 'info'> = {
  low: 'default', medium: 'info', high: 'warning', urgent: 'error',
};

const ALL = 'All';
type SortCol = 'created_at' | 'due_date' | 'priority' | 'status_name';
type SortDir = 'asc' | 'desc';

const PRIORITY_ORDER: Record<string, number> = { low: 0, medium: 1, high: 2, urgent: 3 };

// SLA countdown helper
function SlaChip({ req }: { req: ReportRequest }) {
  if (!req.sla_deadline) return null;
  if (req.sla_overdue) {
    const hrs = req.sla_hours_remaining !== null ? Math.abs(req.sla_hours_remaining) : 0;
    const label = hrs >= 24
      ? `${Math.floor(hrs / 24)}d overdue`
      : `${hrs.toFixed(0)}h overdue`;
    return (
      <Tooltip title="SLA deadline passed">
        <Chip
          size="small"
          icon={<WarningAmberOutlined sx={{ fontSize: '13px !important' }} />}
          label={label}
          color="error"
          variant="outlined"
          sx={{ fontSize: 10, fontWeight: 700, height: 20 }}
        />
      </Tooltip>
    );
  }
  if (req.sla_hours_remaining !== null && req.sla_hours_remaining < 24) {
    return (
      <Tooltip title="SLA deadline approaching">
        <Chip
          size="small"
          label={`${req.sla_hours_remaining.toFixed(0)}h left`}
          color="warning"
          variant="outlined"
          sx={{ fontSize: 10, fontWeight: 700, height: 20 }}
        />
      </Tooltip>
    );
  }
  return null;
}

export function RequestList() {
  const navigate = useNavigate();

  const [requests,    setRequests]    = useState<ReportRequest[]>([]);
  const [departments, setDepartments] = useState<{ id: number; name: string }[]>([]);
  const [misUsers,    setMisUsers]    = useState<{ id: number; full_name: string | null; email: string }[]>([]);
  const [error,       setError]       = useState('');
  const [filtersOpen, setFiltersOpen] = useState(false);

  // ── filter state ────────────────────────────────────────────────────────
  const [search,     setSearch]     = useState('');
  const [statusF,    setStatusF]    = useState(ALL);
  const [priorityF,  setPriorityF]  = useState(ALL);
  const [deptF,      setDeptF]      = useState<number | ''>('');
  const [assigneeF,  setAssigneeF]  = useState<number | ''>('');
  const [dateFrom,   setDateFrom]   = useState('');
  const [dateTo,     setDateTo]     = useState('');
  const [overdueOnly,setOverdueOnly]= useState(false);

  // ── sort state ───────────────────────────────────────────────────────────
  const [sortCol, setSortCol] = useState<SortCol>('created_at');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  // ── saved filters ────────────────────────────────────────────────────────
  const SAVED_FILTERS = [
    { label: 'My overdue',    apply: () => { setOverdueOnly(true); setStatusF(ALL); } },
    { label: 'Unassigned urgent', apply: () => { setPriorityF('urgent'); setAssigneeF(''); setStatusF('Submitted'); } },
    { label: 'Needs action',  apply: () => { setStatusF('Needs Clarification'); } },
  ];

  const clearFilters = useCallback(() => {
    setSearch(''); setStatusF(ALL); setPriorityF(ALL);
    setDeptF(''); setAssigneeF('');
    setDateFrom(''); setDateTo('');
    setOverdueOnly(false);
  }, []);

  const hasActiveFilters = search || statusF !== ALL || priorityF !== ALL ||
    deptF !== '' || assigneeF !== '' || dateFrom || dateTo || overdueOnly;

  const location = useLocation();

  useEffect(() => {
    requestsAPI.list()
      .then((r) => setRequests(r.data))
      .catch(() => setError('Unable to load requests'));

    // Load departments + MIS team for filter dropdowns (silently — not critical)
    requestsAPI.listDepartments()
      .then((r) => setDepartments(r.data))
      .catch(() => undefined);

    usersAPI.misTeam()
      .then((r) => setMisUsers(r.data))
      .catch(() => undefined);
  }, [location.key]);

  const statusOptions = useMemo(() => {
    const s = new Set(requests.map((r) => r.status_name ?? '').filter(Boolean));
    return [ALL, ...Array.from(s).sort()];
  }, [requests]);

  // ── client-side filter + sort ────────────────────────────────────────────
  const filtered = useMemo(() => {
    const q = search.toLowerCase().trim();
    const from = dateFrom ? new Date(dateFrom).getTime() : null;
    const to   = dateTo   ? new Date(dateTo + 'T23:59:59').getTime() : null;

    let results = requests.filter((r) => {
      if (q && !(
        r.title.toLowerCase().includes(q) ||
        (r.description ?? '').toLowerCase().includes(q) ||
        String(r.id).includes(q) ||
        (r.status_name ?? '').toLowerCase().includes(q) ||
        r.priority.toLowerCase().includes(q)
      )) return false;
      if (statusF    !== ALL && r.status_name !== statusF)                return false;
      if (priorityF  !== ALL && r.priority    !== priorityF)              return false;
      if (deptF      !== '' && r.department_id !== deptF)                 return false;
      if (assigneeF  !== '' && r.assigned_to_id !== assigneeF)            return false;
      if (from && new Date(r.created_at).getTime() < from)                return false;
      if (to   && new Date(r.created_at).getTime() > to)                  return false;
      if (overdueOnly && !r.sla_overdue)                                  return false;
      return true;
    });

    results = [...results].sort((a, b) => {
      let va: string | number, vb: string | number;
      switch (sortCol) {
        case 'due_date':    va = new Date(a.due_date).getTime();    vb = new Date(b.due_date).getTime();    break;
        case 'priority':    va = PRIORITY_ORDER[a.priority] ?? 0;   vb = PRIORITY_ORDER[b.priority] ?? 0;   break;
        case 'status_name': va = a.status_name ?? '';               vb = b.status_name ?? '';               break;
        default:            va = new Date(a.created_at).getTime();  vb = new Date(b.created_at).getTime();  break;
      }
      return sortDir === 'asc' ? (va > vb ? 1 : -1) : (va < vb ? 1 : -1);
    });

    return results;
  }, [requests, search, statusF, priorityF, deptF, assigneeF, dateFrom, dateTo, overdueOnly, sortCol, sortDir]);

  const counts = useMemo(() => ({
    open:    requests.filter((r) => !['Closed','Rejected','Cancelled'].includes(r.status_name ?? '')).length,
    pending: requests.filter((r) => ['Pending Dept Approval','Submitted'].includes(r.status_name ?? '')).length,
    inprog:  requests.filter((r) => r.status_name === 'In Progress').length,
    closed:  requests.filter((r) => ['Closed','Resolved'].includes(r.status_name ?? '')).length,
    overdue: requests.filter((r) => r.sla_overdue).length,
  }), [requests]);

  const handleSort = (col: SortCol) => {
    if (sortCol === col) setSortDir((d) => d === 'asc' ? 'desc' : 'asc');
    else { setSortCol(col); setSortDir('desc'); }
  };

  return (
    <Stack spacing={3}>
      {/* header */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 2 }}>
        <Box>
          <Typography variant="h5" fontWeight={700}>Ticket Queue</Typography>
          <Typography variant="body2" color="text.secondary">
            {requests.length} total · {counts.open} open · {counts.inprog} in progress
            {counts.overdue > 0 && (
              <Box component="span" sx={{ color: '#d32f2f', fontWeight: 700, ml: 1 }}>
                · ⚠ {counts.overdue} overdue
              </Box>
            )}
          </Typography>
        </Box>
        <Button
          variant="contained" startIcon={<Add />}
          onClick={() => navigate('/requests/create')}
          sx={{ bgcolor: '#7B1235', '&:hover': { bgcolor: '#5f0d29' } }}
        >
          New request
        </Button>
      </Box>

      {error && <Alert severity="error">{error}</Alert>}

      {/* quick-stat bar */}
      <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
        {[
          { label: 'Open',        value: counts.open,    color: '#7B1235' },
          { label: 'Pending',     value: counts.pending, color: '#a06b32' },
          { label: 'In Progress', value: counts.inprog,  color: '#1565c0' },
          { label: 'Closed',      value: counts.closed,  color: '#2e6b57' },
          ...(counts.overdue > 0 ? [{ label: 'Overdue', value: counts.overdue, color: '#c62828' }] : []),
        ].map((s) => (
          <Paper key={s.label} sx={{ px: 2.5, py: 1.5, borderTop: `3px solid ${s.color}`, minWidth: 110 }}>
            <Typography variant="caption" sx={{ color: s.color, fontWeight: 700, fontSize: 10, letterSpacing: .6, textTransform: 'uppercase' }}>
              {s.label}
            </Typography>
            <Typography sx={{ fontSize: 26, fontWeight: 800, color: s.color, lineHeight: 1.1 }}>{s.value}</Typography>
          </Paper>
        ))}
      </Box>

      {/* search + filter bar */}
      <Paper sx={{ p: 2 }}>
        <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap', alignItems: 'center' }}>
          <TextField
            placeholder="Search by title, ID, status, priority…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            size="small"
            sx={{ flex: 1, minWidth: 220 }}
            slotProps={{ input: { startAdornment: <InputAdornment position="start"><SearchOutlined fontSize="small" sx={{ color: '#7B1235' }} /></InputAdornment> } }}
          />
          <Button
            size="small"
            startIcon={filtersOpen ? <ExpandLess /> : <ExpandMore />}
            onClick={() => setFiltersOpen((v) => !v)}
            variant={hasActiveFilters ? 'contained' : 'outlined'}
            sx={hasActiveFilters ? { bgcolor: '#7B1235', '&:hover': { bgcolor: '#5f0d29' } } : {}}
          >
            Filters {hasActiveFilters ? '•' : ''}
          </Button>
          {hasActiveFilters && (
            <Button size="small" onClick={clearFilters} color="inherit">Clear all</Button>
          )}
        </Box>

        {/* saved quick-filters */}
        <Box sx={{ display: 'flex', gap: 1, mt: 1.5, flexWrap: 'wrap' }}>
          {SAVED_FILTERS.map((f) => (
            <Chip
              key={f.label}
              label={f.label}
              size="small"
              variant="outlined"
              onClick={f.apply}
              sx={{ fontSize: 11, cursor: 'pointer' }}
            />
          ))}
        </Box>

        {/* expanded filter panel */}
        <Collapse in={filtersOpen}>
          <Divider sx={{ my: 2 }} />
          <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap', alignItems: 'center' }}>
            <FilterListOutlined fontSize="small" sx={{ color: '#888' }} />

            <TextField select size="small" label="Status" value={statusF}
              onChange={(e) => setStatusF(e.target.value)} sx={{ minWidth: 180 }}>
              {statusOptions.map((s) => <MenuItem key={s} value={s}>{s}</MenuItem>)}
            </TextField>

            <TextField select size="small" label="Priority" value={priorityF}
              onChange={(e) => setPriorityF(e.target.value)} sx={{ minWidth: 120 }}>
              {[ALL, 'low', 'medium', 'high', 'urgent'].map((p) => (
                <MenuItem key={p} value={p} sx={{ textTransform: 'capitalize' }}>{p}</MenuItem>
              ))}
            </TextField>

            {departments.length > 0 && (
              <TextField select size="small" label="Department" value={deptF}
                onChange={(e) => setDeptF(e.target.value === '' ? '' : Number(e.target.value))}
                sx={{ minWidth: 160 }}>
                <MenuItem value="">All departments</MenuItem>
                {departments.map((d) => <MenuItem key={d.id} value={d.id}>{d.name}</MenuItem>)}
              </TextField>
            )}

            {misUsers.length > 0 && (
              <TextField select size="small" label="Assignee" value={assigneeF}
                onChange={(e) => setAssigneeF(e.target.value === '' ? '' : Number(e.target.value))}
                sx={{ minWidth: 180 }}>
                <MenuItem value="">All assignees</MenuItem>
                {misUsers.map((u) => (
                  <MenuItem key={u.id} value={u.id}>{u.full_name || u.email}</MenuItem>
                ))}
              </TextField>
            )}

            <TextField size="small" label="From date" type="date" value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              slotProps={{ inputLabel: { shrink: true } }} sx={{ minWidth: 150 }} />

            <TextField size="small" label="To date" type="date" value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              slotProps={{ inputLabel: { shrink: true } }} sx={{ minWidth: 150 }} />

            <Chip
              label="Overdue only"
              size="small"
              color={overdueOnly ? 'error' : 'default'}
              variant={overdueOnly ? 'filled' : 'outlined'}
              onClick={() => setOverdueOnly((v) => !v)}
              icon={<WarningAmberOutlined sx={{ fontSize: '14px !important' }} />}
              sx={{ cursor: 'pointer', fontWeight: 600 }}
            />
          </Box>
        </Collapse>

        {hasActiveFilters && (
          <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
            Showing {filtered.length} of {requests.length} tickets
          </Typography>
        )}
      </Paper>

      {/* ticket table */}
      <Paper>
        <Table size="small">
          <TableHead>
            <TableRow sx={{ '& th': { fontWeight: 700, fontSize: 12, color: '#5a4a50', letterSpacing: .4, bgcolor: '#faf7f5' } }}>
              <TableCell sx={{ pl: 2.5 }}>Ticket</TableCell>
              <TableCell>
                <TableSortLabel active={sortCol === 'status_name'} direction={sortCol === 'status_name' ? sortDir : 'asc'}
                  onClick={() => handleSort('status_name')}>Status</TableSortLabel>
              </TableCell>
              <TableCell>
                <TableSortLabel active={sortCol === 'priority'} direction={sortCol === 'priority' ? sortDir : 'asc'}
                  onClick={() => handleSort('priority')}>Priority</TableSortLabel>
              </TableCell>
              <TableCell>
                <TableSortLabel active={sortCol === 'due_date'} direction={sortCol === 'due_date' ? sortDir : 'asc'}
                  onClick={() => handleSort('due_date')}>Due date</TableSortLabel>
              </TableCell>
              <TableCell>SLA</TableCell>
              <TableCell>
                <TableSortLabel active={sortCol === 'created_at'} direction={sortCol === 'created_at' ? sortDir : 'asc'}
                  onClick={() => handleSort('created_at')}>Created</TableSortLabel>
              </TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {filtered.map((r) => (
              <TableRow
                key={r.id} hover
                onClick={() => navigate(`/requests/${r.id}`)}
                sx={{
                  cursor: 'pointer',
                  '&:last-child td': { border: 0 },
                  bgcolor: r.sla_overdue ? '#fff8f8' : undefined,
                }}
              >
                <TableCell sx={{ pl: 2.5, py: 1.5 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    {r.sla_overdue && (
                      <Tooltip title="SLA breached">
                        <WarningAmberOutlined sx={{ fontSize: 16, color: '#d32f2f' }} />
                      </Tooltip>
                    )}
                    <Box>
                      <Typography variant="body2" fontWeight={600}>{r.title}</Typography>
                      <Typography variant="caption" color="text.secondary">
                        #{String(r.id).padStart(5, '0')}
                      </Typography>
                    </Box>
                  </Box>
                </TableCell>
                <TableCell>
                  <Chip size="small" label={r.status_name ?? `#${r.status_id}`}
                    color={STATUS_COLOUR[r.status_name ?? ''] ?? 'default'}
                    sx={{ fontWeight: 600, fontSize: 11 }} />
                </TableCell>
                <TableCell>
                  <Chip size="small" label={r.priority}
                    color={PRIORITY_COLOUR[r.priority] ?? 'default'} variant="outlined"
                    sx={{ fontWeight: 600, fontSize: 11, textTransform: 'capitalize' }} />
                </TableCell>
                <TableCell>
                  <Typography variant="body2">{new Date(r.due_date).toLocaleDateString()}</Typography>
                </TableCell>
                <TableCell><SlaChip req={r} /></TableCell>
                <TableCell>
                  <Typography variant="body2" color="text.secondary">
                    {new Date(r.created_at).toLocaleDateString()}
                  </Typography>
                </TableCell>
              </TableRow>
            ))}
            {filtered.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} sx={{ py: 4, textAlign: 'center' }}>
                  <Typography color="text.secondary">
                    {requests.length === 0 ? 'No tickets yet.' : 'No tickets match your filters.'}
                  </Typography>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Paper>
    </Stack>
  );
}
