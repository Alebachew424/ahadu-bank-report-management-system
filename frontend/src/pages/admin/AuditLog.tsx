/**
 * AuditLog — Admin-only page showing all system audit events.
 * Supports filtering by action, entity type, date range, and keyword search.
 * Provides a one-click CSV export.
 */
import { useEffect, useState, useCallback } from 'react';
import {
  Alert, Box, Button, Chip, CircularProgress,
  Collapse, Divider, IconButton, InputAdornment,
  MenuItem, Paper, Stack, Table, TableBody,
  TableCell, TableHead, TableRow, TextField,
  Tooltip, Typography,
} from '@mui/material';
import {
  DownloadOutlined, ExpandLess, ExpandMore,
  FilterListOutlined, RefreshOutlined, SearchOutlined,
} from '@mui/icons-material';
import { auditAPI } from '../../api/audit';

interface AuditEntry {
  id: number;
  user_id: number | null;
  user_email: string | null;
  action: string;
  entity_type: string;
  entity_id: number | null;
  old_value: Record<string, unknown> | null;
  new_value: Record<string, unknown> | null;
  description: string | null;
  ip_address: string | null;
  created_at: string;
}

const ACTION_COLOUR: Record<string, 'default' | 'success' | 'error' | 'warning' | 'info' | 'primary'> = {
  login_success:          'success',
  login_failed:           'error',
  login_blocked:          'error',
  user_registered:        'info',
  ticket_created:         'primary',
  dept_approved:          'success',
  dept_rejected:          'error',
  ticket_assigned:        'info',
  ticket_started:         'primary',
  ticket_resolved:        'success',
  clarification_requested:'warning',
  ticket_resumed:         'info',
  ticket_cancelled:       'error',
  feedback_submitted:     'success',
  comment_added:          'default',
  status_override:        'warning',
  ticket_updated:         'default',
};

const PAGE_SIZE = 50;

export function AuditLog() {
  const [entries,     setEntries]     = useState<AuditEntry[]>([]);
  const [total,       setTotal]       = useState(0);
  const [skip,        setSkip]        = useState(0);
  const [loading,     setLoading]     = useState(true);
  const [error,       setError]       = useState('');
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [expanded,    setExpanded]    = useState<number | null>(null);

  // meta for filter dropdowns
  const [actions,      setActions]      = useState<string[]>([]);
  const [entityTypes,  setEntityTypes]  = useState<string[]>([]);

  // filters
  const [search,     setSearch]     = useState('');
  const [actionF,    setActionF]    = useState('');
  const [entityF,    setEntityF]    = useState('');
  const [dateFrom,   setDateFrom]   = useState('');
  const [dateTo,     setDateTo]     = useState('');

  const hasFilters = search || actionF || entityF || dateFrom || dateTo;

  // Load dropdown meta once
  useEffect(() => {
    auditAPI.meta()
      .then((r) => { setActions(r.data.actions); setEntityTypes(r.data.entity_types); })
      .catch(() => undefined);
  }, []);

  const load = useCallback((newSkip = 0) => {
    setLoading(true);
    setError('');
    auditAPI.list({
      search:      search || undefined,
      action:      actionF || undefined,
      entity_type: entityF || undefined,
      date_from:   dateFrom || undefined,
      date_to:     dateTo || undefined,
      skip:        newSkip,
      limit:       PAGE_SIZE,
    })
      .then((r) => { setEntries(r.data.results); setTotal(r.data.total); setSkip(newSkip); })
      .catch(() => setError('Unable to load audit logs'))
      .finally(() => setLoading(false));
  }, [search, actionF, entityF, dateFrom, dateTo]);

  useEffect(() => { load(0); }, [load]);

  const exportCSV = () => {
    auditAPI.exportUrl({ search: search || undefined, action: actionF || undefined,
      entity_type: entityF || undefined, date_from: dateFrom || undefined, date_to: dateTo || undefined });
  };

  const clearFilters = () => {
    setSearch(''); setActionF(''); setEntityF(''); setDateFrom(''); setDateTo('');
  };

  const totalPages  = Math.ceil(total / PAGE_SIZE);
  const currentPage = Math.floor(skip / PAGE_SIZE) + 1;

  return (
    <Stack spacing={3}>
      {/* header */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 2 }}>
        <Box>
          <Typography variant="h5" fontWeight={700}>Audit Log</Typography>
          <Typography variant="body2" color="text.secondary">
            Immutable record of all system actions. {total > 0 && `${total.toLocaleString()} entries.`}
          </Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          <Button
            variant="outlined"
            startIcon={<DownloadOutlined />}
            onClick={exportCSV}
            size="small"
          >
            Export CSV
          </Button>
          <IconButton size="small" onClick={() => load(0)} title="Refresh">
            <RefreshOutlined />
          </IconButton>
        </Stack>
      </Box>

      {error && <Alert severity="error">{error}</Alert>}

      {/* search + filter bar */}
      <Paper sx={{ p: 2 }}>
        <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap', alignItems: 'center' }}>
          <TextField
            placeholder="Search descriptions…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && load(0)}
            size="small"
            sx={{ flex: 1, minWidth: 220 }}
            slotProps={{ input: { startAdornment: <InputAdornment position="start"><SearchOutlined fontSize="small" sx={{ color: '#7B1235' }} /></InputAdornment> } }}
          />
          <Button
            size="small"
            startIcon={filtersOpen ? <ExpandLess /> : <ExpandMore />}
            onClick={() => setFiltersOpen((v) => !v)}
            variant={hasFilters ? 'contained' : 'outlined'}
            sx={hasFilters ? { bgcolor: '#7B1235', '&:hover': { bgcolor: '#5f0d29' } } : {}}
          >
            Filters {hasFilters ? '•' : ''}
          </Button>
          {hasFilters && <Button size="small" onClick={clearFilters} color="inherit">Clear</Button>}
        </Box>

        <Collapse in={filtersOpen}>
          <Divider sx={{ my: 2 }} />
          <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
            <FilterListOutlined fontSize="small" sx={{ color: '#888', mt: 1 }} />

            <TextField select size="small" label="Action" value={actionF}
              onChange={(e) => setActionF(e.target.value)} sx={{ minWidth: 210 }}>
              <MenuItem value="">All actions</MenuItem>
              {actions.map((a) => <MenuItem key={a} value={a}>{a}</MenuItem>)}
            </TextField>

            <TextField select size="small" label="Entity type" value={entityF}
              onChange={(e) => setEntityF(e.target.value)} sx={{ minWidth: 150 }}>
              <MenuItem value="">All types</MenuItem>
              {entityTypes.map((t) => <MenuItem key={t} value={t}>{t}</MenuItem>)}
            </TextField>

            <TextField size="small" label="From date" type="date" value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              slotProps={{ inputLabel: { shrink: true } }} sx={{ minWidth: 150 }} />

            <TextField size="small" label="To date" type="date" value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              slotProps={{ inputLabel: { shrink: true } }} sx={{ minWidth: 150 }} />

            <Button variant="contained" size="small"
              sx={{ bgcolor: '#7B1235', '&:hover': { bgcolor: '#5f0d29' }, alignSelf: 'flex-end' }}
              onClick={() => load(0)}>
              Apply
            </Button>
          </Box>
        </Collapse>
      </Paper>

      {/* table */}
      <Paper sx={{ overflowX: 'auto' }}>
        {loading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', p: 6 }}><CircularProgress /></Box>
        ) : (
          <Table size="small">
            <TableHead>
              <TableRow sx={{ '& th': { fontWeight: 700, fontSize: 12, color: '#5a4a50', letterSpacing: .4, bgcolor: '#faf7f5' } }}>
                <TableCell sx={{ pl: 2.5 }}>Timestamp</TableCell>
                <TableCell>Action</TableCell>
                <TableCell>Entity</TableCell>
                <TableCell>User</TableCell>
                <TableCell>Description</TableCell>
                <TableCell>IP</TableCell>
                <TableCell />
              </TableRow>
            </TableHead>
            <TableBody>
              {entries.map((e) => (
                <>
                  <TableRow
                    key={e.id}
                    hover
                    sx={{ cursor: 'pointer', '&:last-child td': { border: 0 } }}
                    onClick={() => setExpanded(expanded === e.id ? null : e.id)}
                  >
                    <TableCell sx={{ pl: 2.5, whiteSpace: 'nowrap' }}>
                      <Typography variant="caption" sx={{ fontFamily: 'monospace' }}>
                        {new Date(e.created_at).toLocaleString()}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Chip
                        size="small"
                        label={e.action.replace(/_/g, ' ')}
                        color={ACTION_COLOUR[e.action] ?? 'default'}
                        sx={{ fontSize: 10, fontWeight: 700, textTransform: 'capitalize' }}
                      />
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">
                        {e.entity_type}
                        {e.entity_id ? <Box component="span" sx={{ color: '#999', ml: .5 }}>#{e.entity_id}</Box> : null}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" noWrap sx={{ maxWidth: 180 }}>
                        {e.user_email ?? <Box component="span" sx={{ color: '#bbb' }}>system</Box>}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" noWrap sx={{ maxWidth: 260 }}>
                        {e.description}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="caption" sx={{ fontFamily: 'monospace', color: '#999' }}>
                        {e.ip_address}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Tooltip title={expanded === e.id ? 'Hide detail' : 'Show detail'}>
                        <IconButton size="small">
                          {expanded === e.id ? <ExpandLess fontSize="small" /> : <ExpandMore fontSize="small" />}
                        </IconButton>
                      </Tooltip>
                    </TableCell>
                  </TableRow>

                  {/* expanded detail row */}
                  {expanded === e.id && (
                    <TableRow key={`${e.id}-detail`} sx={{ bgcolor: '#fdf9f5' }}>
                      <TableCell colSpan={7} sx={{ py: 1.5, px: 3 }}>
                        <Box sx={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                          {e.old_value && (
                            <Box>
                              <Typography variant="caption" fontWeight={700} sx={{ color: '#c62828', display: 'block', mb: .5 }}>
                                Before
                              </Typography>
                              <Box component="pre" sx={{ m: 0, fontSize: 12, fontFamily: 'monospace', color: '#444' }}>
                                {JSON.stringify(e.old_value, null, 2)}
                              </Box>
                            </Box>
                          )}
                          {e.new_value && (
                            <Box>
                              <Typography variant="caption" fontWeight={700} sx={{ color: '#2e6b57', display: 'block', mb: .5 }}>
                                After
                              </Typography>
                              <Box component="pre" sx={{ m: 0, fontSize: 12, fontFamily: 'monospace', color: '#444' }}>
                                {JSON.stringify(e.new_value, null, 2)}
                              </Box>
                            </Box>
                          )}
                          {!e.old_value && !e.new_value && (
                            <Typography variant="caption" color="text.secondary">No value diff recorded.</Typography>
                          )}
                        </Box>
                      </TableCell>
                    </TableRow>
                  )}
                </>
              ))}
              {entries.length === 0 && !loading && (
                <TableRow>
                  <TableCell colSpan={7} sx={{ py: 4, textAlign: 'center' }}>
                    <Typography color="text.secondary">No audit log entries found.</Typography>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        )}
      </Paper>

      {/* pagination */}
      {total > PAGE_SIZE && (
        <Box sx={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: 2 }}>
          <Typography variant="body2" color="text.secondary">
            Page {currentPage} of {totalPages} · {total.toLocaleString()} entries
          </Typography>
          <Button size="small" disabled={skip === 0} onClick={() => load(skip - PAGE_SIZE)}>← Prev</Button>
          <Button size="small" disabled={skip + PAGE_SIZE >= total} onClick={() => load(skip + PAGE_SIZE)}>Next →</Button>
        </Box>
      )}
    </Stack>
  );
}
