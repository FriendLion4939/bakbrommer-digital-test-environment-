/* GENERATED FILE - do not edit.
 * Made from interface.py by: python -m bakbrommer_twin.control.sil.header
 *
 * Interface between the simulated vehicle and controller code written in C.
 * All values are doubles in SI units (see the comment behind each field).
 */
#ifndef BB_CONTROLLER_H
#define BB_CONTROLLER_H

#ifdef _WIN32
#define BB_API __declspec(dllexport)
#else
#define BB_API
#endif

/* What the controller reads every control period. */
typedef struct {
    double time;  /* s since start */
    double dt;  /* s since the previous controller step */
    double throttle;  /* twist grip position, 0…1 */
    double brake_front_pressure;  /* Pa */
    double brake_rear_pressure;  /* Pa */
    double steering_angle;  /* handlebar angle, rad (+ = left) */
    double engine_speed;  /* rad/s */
    double vehicle_speed;  /* m/s */
    double wheel_speed_fl;  /* rad/s */
    double wheel_speed_fr;  /* rad/s */
    double wheel_speed_r;  /* rad/s */
    double accel_x;  /* m/s², forward (specific force, includes gravity) */
    double accel_y;  /* m/s², left */
    double accel_z;  /* m/s², up */
    double gyro_x;  /* rad/s, roll rate */
    double gyro_y;  /* rad/s, pitch rate */
    double gyro_z;  /* rad/s, yaw rate */
    double battery_voltage;  /* V */
    double battery_current;  /* A (+ = discharging) */
    double motor_temp_l;  /* °C */
    double motor_temp_r;  /* °C */
    double mode_request;  /* ride mode switch position (index into RIDE_MODES) */
} bb_inputs_t;

/* What the controller writes every control period. */
typedef struct {
    double torque_left;  /* Nm at the left front wheel (+ drive, − regen) */
    double torque_right;  /* Nm at the right front wheel */
    double engine_throttle;  /* 0…1, used only with throttle-by-wire */
    double engine_ignition;  /* 1 = petrol engine may run, 0 = cut */
    double engine_starter;  /* 1 = crank the petrol engine */
    double active_mode;  /* ride mode in effect (index into RIDE_MODES) */
    double diag_speed_estimate;  /* m/s, controller's own speed estimate */
    double diag_traction_left;  /* 0…1, share of torque removed by traction control */
    double diag_traction_right;  /* 0…1 */
    double diag_vectoring_torque;  /* Nm moved from the left to the right wheel */
    double diag_regen_torque;  /* Nm of electric braking requested per wheel */
    double diag_power_limit;  /* 0…1, torque factor from battery/thermal limits */
    double diag_stability_limit;  /* 0…1, torque factor from rollover protection */
} bb_outputs_t;

/* Functions a controller library must provide: */

/* Number of tuning parameters the controller wants from the simulator. */
BB_API int bb_param_count(void);
/* Dotted registry name of parameter `index`, e.g. "control.limits.battery_current". */
BB_API const char *bb_param_name(int index);
/* Called once per parameter before the run; `value` is in SI units. */
BB_API void bb_set_param(int index, double value);
/* Return to the power-on state. */
BB_API void bb_reset(void);
/* One control period: read `in`, fill `out`. */
BB_API void bb_step(const bb_inputs_t *in, bb_outputs_t *out);

#endif /* BB_CONTROLLER_H */
