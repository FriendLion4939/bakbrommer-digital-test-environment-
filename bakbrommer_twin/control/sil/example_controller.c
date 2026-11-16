/* Example controller in C for software-in-the-loop.
 *
 * A deliberately small hybrid logic, written the way firmware is written
 * (static state, no heap), to show how real STM32 control code plugs into the
 * simulator:
 *   - motor torque = throttle x torque at full throttle (Normal mode value)
 *   - both motors get the same torque (no traction control, no vectoring)
 *   - torque is scaled down so the predicted battery current stays below the limit
 *   - front brake pressure above a threshold gives regenerative braking
 *   - torque changes are rate limited
 *   - the petrol engine is always allowed to run
 *
 * To use your own firmware code instead: keep bb_controller.h, replace the
 * body of bb_step() by a call into your control function, and list the tuning
 * values you need in PARAM_NAMES. See docs/SIL.md.
 */
#include "bb_controller.h"

enum {
    P_ELECTRIC_TORQUE,
    P_BRAKE_REGEN_TORQUE,
    P_BRAKE_THRESHOLD,
    P_FULL_PRESSURE,
    P_BATTERY_CURRENT,
    P_EFFICIENCY,
    P_TORQUE_RATE,
    PARAM_COUNT
};

static const char *const PARAM_NAMES[PARAM_COUNT] = {
    "control.mode_normal.electric_torque", /* Nm */
    "control.mode_normal.brake_regen_torque", /* Nm */
    "control.regen.brake_threshold", /* Pa */
    "control.regen.full_pressure", /* Pa */
    "control.limits.battery_current", /* A */
    "control.limits.assumed_efficiency", /* 0..1 */
    "control.torque_rate_limit", /* Nm/s */
};

static double params[PARAM_COUNT];
static double torque_now; /* last commanded torque per motor, Nm */

static double clamp(double value, double low, double high)
{
    return value < low ? low : (value > high ? high : value);
}

BB_API int bb_param_count(void) { return PARAM_COUNT; }

BB_API const char *bb_param_name(int index)
{
    return (index >= 0 && index < PARAM_COUNT) ? PARAM_NAMES[index] : "";
}

BB_API void bb_set_param(int index, double value)
{
    if (index >= 0 && index < PARAM_COUNT) {
        params[index] = value;
    }
}

BB_API void bb_reset(void) { torque_now = 0.0; }

BB_API void bb_step(const bb_inputs_t *in, bb_outputs_t *out)
{
    double throttle = clamp(in->throttle, 0.0, 1.0);
    double wanted;
    double regen = 0.0;
    double limit_factor = 1.0;

    if (in->brake_front_pressure > params[P_BRAKE_THRESHOLD]) {
        /* braking: regen in proportion to the brake pressure */
        double brake = (in->brake_front_pressure - params[P_BRAKE_THRESHOLD]) /
                       (params[P_FULL_PRESSURE] - params[P_BRAKE_THRESHOLD]);
        regen = clamp(brake, 0.0, 1.0) * params[P_BRAKE_REGEN_TORQUE];
        wanted = -regen;
    } else {
        double wheel_speed = 0.5 * (in->wheel_speed_fl + in->wheel_speed_fr); /* rad/s */
        double power, current;
        wanted = throttle * params[P_ELECTRIC_TORQUE];
        /* predicted battery current of both motors: P / (efficiency x voltage) */
        power = 2.0 * wanted * (wheel_speed > 0.0 ? wheel_speed : 0.0);
        current = power / (params[P_EFFICIENCY] * (in->battery_voltage > 1.0 ? in->battery_voltage : 1.0));
        if (current > params[P_BATTERY_CURRENT]) {
            limit_factor = params[P_BATTERY_CURRENT] / current;
            wanted *= limit_factor;
        }
    }

    /* rate limit */
    {
        double step = params[P_TORQUE_RATE] * in->dt;
        torque_now += clamp(wanted - torque_now, -step, step);
    }

    out->torque_left = torque_now;
    out->torque_right = torque_now;
    out->engine_throttle = throttle;
    out->engine_ignition = 1.0;
    out->engine_starter = 0.0;
    out->active_mode = in->mode_request;
    out->diag_speed_estimate = in->vehicle_speed;
    out->diag_traction_left = 0.0;
    out->diag_traction_right = 0.0;
    out->diag_vectoring_torque = 0.0;
    out->diag_regen_torque = regen;
    out->diag_power_limit = limit_factor;
    out->diag_stability_limit = 1.0;
}
