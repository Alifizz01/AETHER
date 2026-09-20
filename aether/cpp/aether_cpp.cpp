#include <pybind11/pybind11.h>

namespace py = pybind11;

double terminal_voltage(
    double soc,
    double current,
    double capacity,
    double r_internal,
    double u_empty,
    double u_full
){
    double u_ocv = u_empty + soc * (u_full - u_empty);
    return u_ocv - current * r_internal;
}