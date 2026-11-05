function outputDir = build_dab_sps(runSimulation)
%BUILD_DAB_SPS Build a standard-block Simulink DAB SPS teaching model.
% build_dab_sps() runs +/-30 degree zero-current startups at two step sizes.
% build_dab_sps(false) only saves the model. MATLAB + Simulink are required;
% no Simscape or hardware access is used. NOT executed in this repository's
% current environment. See docs/SIMULINK.md for scope and pending validation.
if nargin == 0
    runSimulation = true;
end
validateattributes(runSimulation, {'logical'}, {'scalar'});
root = fileparts(fileparts(fileparts(mfilename('fullpath'))));
runsDir = fullfile(root, '.runs');
if ~isfolder(runsDir)
    mkdir(runsDir);
end
outputDir = tempname(runsDir);
mkdir(outputDir);
diary(fullfile(outputDir, 'matlab.log'));
diaryCleanup = onCleanup(@() diary('off')); %#ok<NASGU>
fprintf('Output: %s\nMATLAB: %s\n', outputDir, version);
try
p = struct('V1_V', 24, 'V2_V', 12, 'n', 2, 'L_H', 100e-6, ...
    'R_ohm', 0.5, 'fs_Hz', 20000, 'initial_current_A', 0, ...
    'periods', 120, 'edge_grid_per_period', 600);
p.period_s = 1 / p.fs_Hz;
p.stop_s = p.periods * p.period_s;
p.rise_fall_s = p.period_s / p.edge_grid_per_period;
save(fullfile(outputDir, 'parameters.mat'), 'p');

model = 'dab_sps_teaching';
if bdIsLoaded(model)
    error('DAB:ModelOpen', 'Save and close the already loaded %s before building.', model);
end
load_system('simulink');
new_system(model);
modelCleanup = onCleanup(@() close_system(model, 0)); %#ok<NASGU>
set_param(model, 'SolverType', 'Fixed-step', 'Solver', 'ode4', ...
    'FixedStep', number(p.rise_fall_s), 'StopTime', number(p.stop_s), ...
    'ReturnWorkspaceOutputs', 'on', 'SaveTime', 'off', ...
    'SaveOutput', 'off', 'SignalLogging', 'off');
% Default input is saved inside the SLX, not in the user's base workspace.
[drive1, drive2] = bridge_drives(p, 30);
workspace = get_param(model, 'ModelWorkspace');
workspace.DataSource = 'Model File';
assignin(workspace, 'drive1', drive1);
assignin(workspace, 'drive2', drive2);
add_block('simulink/Sources/From Workspace', [model '/Bridge1'], ...
    'VariableName', 'drive1', 'SampleTime', '0', 'Interpolate', 'on', ...
    'ZeroCross', 'off', 'OutputAfterFinalValue', 'Holding final value', ...
    'Position', [30 60 150 90]);
add_block('simulink/Sources/From Workspace', [model '/Bridge2Referred'], ...
    'VariableName', 'drive2', 'SampleTime', '0', 'Interpolate', 'on', ...
    'ZeroCross', 'off', 'OutputAfterFinalValue', 'Holding final value', ...
    'Position', [30 140 150 170]);
add_block('simulink/Math Operations/Sum', [model '/InductorVoltage'], ...
    'Inputs', '+--', 'Position', [220 65 250 135]);
add_block('simulink/Math Operations/Gain', [model '/InverseL'], ...
    'Gain', number(1 / p.L_H), 'Position', [300 80 370 120]);
add_block('simulink/Continuous/Integrator', [model '/Current'], ...
    'InitialCondition', number(p.initial_current_A), 'Position', [420 80 450 120]);
add_block('simulink/Math Operations/Gain', [model '/SeriesR'], ...
    'Gain', number(p.R_ohm), 'Position', [300 200 370 240]);
add_block('simulink/Signal Routing/Mux', [model '/Waveforms'], ...
    'Inputs', '3', 'Position', [530 55 535 145]);
add_block('simulink/Sinks/To Workspace', [model '/Log'], ...
    'VariableName', 'waveforms', 'SaveFormat', 'Timeseries', ...
    'MaxDataPoints', 'inf', 'Decimation', '1', 'SampleTime', '-1', ...
    'Position', [590 80 700 120]);
connections = {'Bridge1/1', 'InductorVoltage/1'; ...
    'Bridge2Referred/1', 'InductorVoltage/2'; 'SeriesR/1', 'InductorVoltage/3'; ...
    'InductorVoltage/1', 'InverseL/1'; 'InverseL/1', 'Current/1'; ...
    'Current/1', 'SeriesR/1'; 'Bridge1/1', 'Waveforms/1'; ...
    'Bridge2Referred/1', 'Waveforms/2'; 'Current/1', 'Waveforms/3'; ...
    'Waveforms/1', 'Log/1'};
for k = 1:size(connections, 1)
    add_line(model, connections{k, 1}, connections{k, 2}, 'autorouting', 'on');
end
save_system(model, fullfile(outputDir, [model '.slx']));
if ~runSimulation
    fprintf('Built model only; no simulation was requested.\n');
    return;
end

results = struct([]);
for phase = [30, -30]
    [drive1, drive2] = bridge_drives(p, phase);
    for refinement = [1, 2]
        step = p.rise_fall_s / refinement;
        input = Simulink.SimulationInput(model);
        input = input.setVariable('drive1', drive1, 'Workspace', model);
        input = input.setVariable('drive2', drive2, 'Workspace', model);
        input = input.setModelParameter('FixedStep', number(step));
        output = sim(input);
        signal = output.get('waveforms');
        t = signal.Time(:);
        x = signal.Data;
        label = sprintf('phase_%+03d_step_%d', phase, refinement);
        % Preserve actual output before evaluating correctness.
        save(fullfile(outputDir, [label '.mat']), 'output', 'phase', 'step', 'p');
        assert(size(x, 2) == 3 && numel(t) == size(x, 1), 'Unexpected waveform dimensions.');
        assert(all(isfinite(t)) && all(isfinite(x(:))) && all(diff(t) > 0), ...
            'Expected finite, increasing-time waveform data.');
        assert(abs(t(1)) < 1e-12 && abs(t(end) - p.stop_s) < 1e-12, ...
            'Simulation did not cover the requested time interval.');
        assert(max(abs(diff(t) - step)) < 1e-12, 'Expected fixed-step output.');
        expected1 = interp1(drive1(:, 1), drive1(:, 2), t, 'linear');
        expected2 = interp1(drive2(:, 1), drive2(:, 2), t, 'linear');
        iReference = reference_current(t, expected1 - expected2, p);
        assert(all(isfinite(expected1)) && all(isfinite(expected2)) && all(isfinite(iReference)), ...
            'Reference inputs do not cover the logged time interval.');
        p1 = x(:, 1) .* x(:, 3);
        p2 = x(:, 2) .* x(:, 3);
        pr = p.R_ohm * x(:, 3).^2;
        energyResidual = cumtrapz(t, p1 - p2 - pr) ...
            - 0.5 * p.L_H * (x(:, 3).^2 - x(1, 3)^2);
        waveform = table(t, x(:, 1), x(:, 2), x(:, 3), iReference, ...
            p1, p2, pr, energyResidual, 'VariableNames', ...
            {'time_s', 'v1_V', 'v2_referred_V', 'iL_A', 'reference_iL_A', ...
            'p1_W', 'p2_W', 'resistor_W', 'energy_residual_J'});
        writetable(waveform, fullfile(outputDir, [label '.csv']));
        tail = t >= p.stop_s - 10 * p.period_s - 1e-12;
        span = t(find(tail, 1, 'last')) - t(find(tail, 1));
        r = struct('phase_deg', phase, 'refinement', refinement, 'step_s', step, ...
            'p1_tail_W', trapz(t(tail), p1(tail)) / span, ...
            'p2_tail_W', trapz(t(tail), p2(tail)) / span, ...
            'resistor_tail_W', trapz(t(tail), pr(tail)) / span, ...
            'i_rms_tail_A', sqrt(trapz(t(tail), x(tail, 3).^2) / span), ...
            'max_reference_error_A', max(abs(x(:, 3) - iReference)), ...
            'max_energy_residual_J', max(abs(energyResidual)), ...
            'max_source_error_V', max([abs(x(:, 1) - expected1); abs(x(:, 2) - expected2)]));
        results = [results; r]; %#ok<AGROW>
        writetable(struct2table(results), fullfile(outputDir, 'metrics.csv'));
        assert(abs(x(1, 3) - p.initial_current_A) < 1e-10, 'Initial current changed.');
        assert(r.max_source_error_V < 1e-8, 'Unexpected bridge source values.');
        assert(r.max_reference_error_A < 1e-5, 'RL reference comparison failed.');
        assert(r.max_energy_residual_J < 1e-6, 'Energy balance check failed.');
        assert(sign(r.p2_tail_W) == sign(phase), 'Power direction check failed.');
    end
end
for k = [1, 3]
    assert(abs(results(k).p2_tail_W - results(k+1).p2_tail_W) < 0.01, ...
        'Two-step power comparison failed; inspect saved waveforms.');
    assert(abs(results(k).i_rms_tail_A - results(k+1).i_rms_tail_A) < 1e-4, ...
        'Two-step current comparison failed; inspect saved waveforms.');
end
fprintf('Four Simulink runs and finite-scope checks completed successfully.\n');
catch failure
    fprintf(2, '%s\n', getReport(failure, 'extended', 'hyperlinks', 'off'));
    rethrow(failure);
end
end

function [drive1, drive2] = bridge_drives(p, phase)
% Finite linear edges occupy one base interval before each nominal edge.
% Both bridges share this convention, preserving their relative phase.
grid = (0:p.periods * p.edge_grid_per_period)';
t = grid * p.rise_fall_s;
t(end) = p.stop_s;
delay = phase / 360 * p.edge_grid_per_period;
assert(abs(delay - round(delay)) < 1e-12, 'Phase must align to the edge grid.');
v1 = p.V1_V * (2 * (mod(grid, p.edge_grid_per_period) < p.edge_grid_per_period / 2) - 1);
v2 = p.n * p.V2_V * (2 * (mod(grid - round(delay), p.edge_grid_per_period) < p.edge_grid_per_period / 2) - 1);
drive1 = edge_points(t, v1);
drive2 = edge_points(t, v2);
end

function drive = edge_points(t, v)
changes = find(diff(v) ~= 0) + 1;
keep = unique([1; changes - 1; changes; numel(t)]);
drive = [t(keep), v(keep)];
end

function i = reference_current(t, voltage, p)
% Exact update for L di/dt + R i = v0 + slope*(t-t0) on an aligned step.
% It does not use the Simulink current state.
i = zeros(size(t));
i(1) = p.initial_current_A;
tau = p.L_H / p.R_ohm;
for k = 1:numel(t)-1
    dt = t(k+1) - t(k);
    z = -expm1(-dt / tau);
    slope = (voltage(k+1) - voltage(k)) / dt;
    i(k+1) = (1 - z) * i(k) + voltage(k) / p.R_ohm * z ...
        + slope / p.R_ohm * (dt - tau * z);
end
end

function text = number(value)
text = sprintf('%.17g', value);
end
