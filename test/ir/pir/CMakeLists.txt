file(
  GLOB TEST_INTERP_CASES
  RELATIVE "${CMAKE_CURRENT_SOURCE_DIR}"
  "test_*.py")
string(REPLACE ".py" "" TEST_INTERP_CASES "${TEST_INTERP_CASES}")

set(TEST_IR_SYSTEM_CASES
    test_build_model
    test_if_api
    test_while_api
    test_assert_api
    test_lr_scheduler_in_pir
    test_pd_inplace_pass
    test_symbol_overload
    test_pir_to_static
    test_stop_gradient
    test_cse_pass
    test_override_operator
    test_ir_save_load)
list(REMOVE_ITEM TEST_INTERP_CASES ${TEST_IR_SYSTEM_CASES})
list(REMOVE_ITEM TEST_INTERP_CASES test_subgraph_exporter)

foreach(target ${TEST_INTERP_CASES})
  py_test_modules(${target} MODULES ${target} ENVS GLOG_v=1
                  FLAGS_enable_pir_in_executor=true)
endforeach()

foreach(target ${TEST_IR_SYSTEM_CASES})
  py_test_modules(${target} MODULES ${target} ENVS FLAGS_enable_pir_api=true)
endforeach()

set_tests_properties(test_pd_inplace_pass PROPERTIES TIMEOUT 60)
set_tests_properties(test_map_op_another_pass PROPERTIES TIMEOUT 60)

py_test_modules(
  test_subgraph_exporter
  MODULES
  test_subgraph_exporter
  ENVS
  MIN_GRAPH_SIZE=0
  FLAGS_enable_pir_in_executor=1
  FLAGS_pir_subgraph_saving_dir=${CMAKE_CURRENT_SOURCE_DIR})

add_subdirectory(fused_pass)
add_subdirectory(translator)
