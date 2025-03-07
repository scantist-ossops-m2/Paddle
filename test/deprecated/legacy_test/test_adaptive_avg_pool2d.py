#   Copyright (c) 2020 PaddlePaddle Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import unittest

import numpy as np
from test_attribute_var_deprecated import UnittestBase

import paddle
from paddle.base import Program, core, program_guard
from paddle.pir_utils import test_with_pir_api


def adaptive_start_index(index, input_size, output_size):
    return int(np.floor(index * input_size / output_size))


def adaptive_end_index(index, input_size, output_size):
    return int(np.ceil((index + 1) * input_size / output_size))


def adaptive_pool2d_forward(
    x, output_size, data_format='NCHW', pool_type="avg"
):
    N = x.shape[0]
    C, H, W = (
        [x.shape[1], x.shape[2], x.shape[3]]
        if data_format == 'NCHW'
        else [x.shape[3], x.shape[1], x.shape[2]]
    )

    if isinstance(output_size, int) or output_size is None:
        H_out = output_size
        W_out = output_size
        output_size = [H_out, W_out]
    else:
        H_out, W_out = output_size

    if output_size[0] is None:
        output_size[0] = H
        H_out = H
    if output_size[1] is None:
        output_size[1] = W
        W_out = W

    out = (
        np.zeros((N, C, H_out, W_out))
        if data_format == 'NCHW'
        else np.zeros((N, H_out, W_out, C))
    )

    for i in range(H_out):
        in_h_start = adaptive_start_index(i, H, output_size[0])
        in_h_end = adaptive_end_index(i, H, output_size[0])

        for j in range(W_out):
            in_w_start = adaptive_start_index(j, W, output_size[1])
            in_w_end = adaptive_end_index(j, W, output_size[1])

            if data_format == 'NCHW':
                x_masked = x[:, :, in_h_start:in_h_end, in_w_start:in_w_end]
                if pool_type == 'avg':
                    field_size = (in_h_end - in_h_start) * (
                        in_w_end - in_w_start
                    )
                    out[:, :, i, j] = np.sum(x_masked, axis=(2, 3)) / field_size
                elif pool_type == 'max':
                    out[:, :, i, j] = np.max(x_masked, axis=(2, 3))
            elif data_format == 'NHWC':
                x_masked = x[:, in_h_start:in_h_end, in_w_start:in_w_end, :]
                if pool_type == 'avg':
                    field_size = (in_h_end - in_h_start) * (
                        in_w_end - in_w_start
                    )
                    out[:, i, j, :] = np.sum(x_masked, axis=(1, 2)) / field_size
                elif pool_type == 'max':
                    out[:, i, j, :] = np.max(x_masked, axis=(1, 2))
    return out


class TestAdaptiveAvgPool2DAPI(unittest.TestCase):
    def setUp(self):
        self.x_np = np.random.random([2, 3, 7, 7]).astype("float32")
        self.res_1_np = adaptive_pool2d_forward(
            x=self.x_np, output_size=[3, 3], pool_type="avg"
        )

        self.res_2_np = adaptive_pool2d_forward(
            x=self.x_np, output_size=5, pool_type="avg"
        )

        self.res_3_np = adaptive_pool2d_forward(
            x=self.x_np, output_size=[2, 5], pool_type="avg"
        )

        self.res_4_np = adaptive_pool2d_forward(
            x=self.x_np, output_size=[3, 3], pool_type="avg", data_format="NHWC"
        )

        self.res_5_np = adaptive_pool2d_forward(
            x=self.x_np, output_size=[None, 3], pool_type="avg"
        )

    @test_with_pir_api
    def test_static_graph(self):
        for use_cuda in (
            [False, True] if core.is_compiled_with_cuda() else [False]
        ):
            place = paddle.CUDAPlace(0) if use_cuda else paddle.CPUPlace()
            paddle.enable_static()

            main_program = paddle.static.Program()
            startup_program = paddle.static.Program()

            with paddle.static.program_guard(main_program, startup_program):
                x = paddle.static.data(
                    name="x", shape=[2, 3, 7, 7], dtype="float32"
                )

                out_1 = paddle.nn.functional.adaptive_avg_pool2d(
                    x=x, output_size=[3, 3]
                )

                out_2 = paddle.nn.functional.adaptive_avg_pool2d(
                    x=x, output_size=5
                )

                out_3 = paddle.nn.functional.adaptive_avg_pool2d(
                    x=x, output_size=[2, 5]
                )

                out_4 = paddle.nn.functional.adaptive_avg_pool2d(
                    x=x, output_size=[3, 3], data_format="NHWC"
                )

                out_5 = paddle.nn.functional.adaptive_avg_pool2d(
                    x=x, output_size=[None, 3]
                )

            exe = paddle.static.Executor(place=place)
            [res_1, res_2, res_3, res_4, res_5] = exe.run(
                main_program,
                feed={"x": self.x_np},
                fetch_list=[out_1, out_2, out_3, out_4, out_5],
            )

            np.testing.assert_allclose(
                res_1, self.res_1_np, rtol=1e-5, atol=1e-8
            )
            np.testing.assert_allclose(
                res_2, self.res_2_np, rtol=1e-5, atol=1e-8
            )
            np.testing.assert_allclose(
                res_3, self.res_3_np, rtol=1e-5, atol=1e-8
            )
            np.testing.assert_allclose(
                res_4, self.res_4_np, rtol=1e-5, atol=1e-8
            )
            np.testing.assert_allclose(
                res_5, self.res_5_np, rtol=1e-5, atol=1e-8
            )

    def test_dynamic_graph(self):
        for use_cuda in (
            [False, True] if core.is_compiled_with_cuda() else [False]
        ):
            place = paddle.CUDAPlace(0) if use_cuda else paddle.CPUPlace()
            paddle.disable_static(place=place)
            x = paddle.to_tensor(self.x_np)

            out_1 = paddle.nn.functional.adaptive_avg_pool2d(
                x=x, output_size=[3, 3]
            )
            out_2 = paddle.nn.functional.adaptive_avg_pool2d(x=x, output_size=5)
            out_3 = paddle.nn.functional.adaptive_avg_pool2d(
                x=x, output_size=[2, 5]
            )
            out_4 = paddle.nn.functional.adaptive_avg_pool2d(
                x=x, output_size=[3, 3], data_format="NHWC"
            )
            out_5 = paddle.nn.functional.adaptive_avg_pool2d(
                x=x, output_size=[None, 3]
            )
            out_6 = paddle.nn.functional.interpolate(
                x=x, mode="area", size=[2, 5]
            )

            np.testing.assert_allclose(
                out_1.numpy(), self.res_1_np, rtol=1e-5, atol=1e-8
            )
            np.testing.assert_allclose(
                out_2.numpy(), self.res_2_np, rtol=1e-5, atol=1e-8
            )
            np.testing.assert_allclose(
                out_3.numpy(), self.res_3_np, rtol=1e-5, atol=1e-8
            )
            np.testing.assert_allclose(
                out_4.numpy(), self.res_4_np, rtol=1e-5, atol=1e-8
            )
            np.testing.assert_allclose(
                out_5.numpy(), self.res_5_np, rtol=1e-5, atol=1e-8
            )
            np.testing.assert_allclose(
                out_6.numpy(), self.res_3_np, rtol=1e-5, atol=1e-8
            )


class TestAdaptiveAvgPool2DClassAPI(unittest.TestCase):
    def setUp(self):
        self.x_np = np.random.random([2, 3, 7, 7]).astype("float32")
        self.res_1_np = adaptive_pool2d_forward(
            x=self.x_np, output_size=[3, 3], pool_type="avg"
        )

        self.res_2_np = adaptive_pool2d_forward(
            x=self.x_np, output_size=5, pool_type="avg"
        )

        self.res_3_np = adaptive_pool2d_forward(
            x=self.x_np, output_size=[2, 5], pool_type="avg"
        )

        self.res_4_np = adaptive_pool2d_forward(
            x=self.x_np, output_size=[3, 3], pool_type="avg", data_format="NHWC"
        )

        self.res_5_np = adaptive_pool2d_forward(
            x=self.x_np, output_size=[None, 3], pool_type="avg"
        )

    @test_with_pir_api
    def test_static_graph(self):
        for use_cuda in (
            [False, True] if core.is_compiled_with_cuda() else [False]
        ):
            place = paddle.CUDAPlace(0) if use_cuda else paddle.CPUPlace()
            paddle.enable_static()
            main_program = paddle.static.Program()
            startup_program = paddle.static.Program()

            with paddle.static.program_guard(main_program, startup_program):
                x = paddle.static.data(
                    name="x", shape=[2, 3, 7, 7], dtype="float32"
                )

                adaptive_avg_pool = paddle.nn.AdaptiveAvgPool2D(
                    output_size=[3, 3]
                )
                out_1 = adaptive_avg_pool(x=x)

                adaptive_avg_pool = paddle.nn.AdaptiveAvgPool2D(output_size=5)
                out_2 = adaptive_avg_pool(x=x)

                adaptive_avg_pool = paddle.nn.AdaptiveAvgPool2D(
                    output_size=[2, 5]
                )
                out_3 = adaptive_avg_pool(x=x)

                adaptive_avg_pool = paddle.nn.AdaptiveAvgPool2D(
                    output_size=[3, 3], data_format="NHWC"
                )
                out_4 = adaptive_avg_pool(x=x)

                adaptive_avg_pool = paddle.nn.AdaptiveAvgPool2D(
                    output_size=[None, 3]
                )
                out_5 = adaptive_avg_pool(x=x)

            exe = paddle.static.Executor(place=place)
            [res_1, res_2, res_3, res_4, res_5] = exe.run(
                main_program,
                feed={"x": self.x_np},
                fetch_list=[out_1, out_2, out_3, out_4, out_5],
            )

            np.testing.assert_allclose(
                res_1, self.res_1_np, rtol=1e-5, atol=1e-8
            )
            np.testing.assert_allclose(
                res_2, self.res_2_np, rtol=1e-5, atol=1e-8
            )
            np.testing.assert_allclose(
                res_3, self.res_3_np, rtol=1e-5, atol=1e-8
            )
            np.testing.assert_allclose(
                res_4, self.res_4_np, rtol=1e-5, atol=1e-8
            )
            np.testing.assert_allclose(
                res_5, self.res_5_np, rtol=1e-5, atol=1e-8
            )

    def test_dynamic_graph(self):
        for use_cuda in (
            [False, True] if core.is_compiled_with_cuda() else [False]
        ):
            place = paddle.CUDAPlace(0) if use_cuda else paddle.CPUPlace()
            paddle.disable_static(place=place)
            x = paddle.to_tensor(self.x_np)

            adaptive_avg_pool = paddle.nn.AdaptiveAvgPool2D(output_size=[3, 3])
            out_1 = adaptive_avg_pool(x=x)

            adaptive_avg_pool = paddle.nn.AdaptiveAvgPool2D(output_size=5)
            out_2 = adaptive_avg_pool(x=x)

            adaptive_avg_pool = paddle.nn.AdaptiveAvgPool2D(output_size=[2, 5])
            out_3 = adaptive_avg_pool(x=x)

            adaptive_avg_pool = paddle.nn.AdaptiveAvgPool2D(
                output_size=[3, 3], data_format="NHWC"
            )
            out_4 = adaptive_avg_pool(x=x)

            adaptive_avg_pool = paddle.nn.AdaptiveAvgPool2D(
                output_size=[None, 3]
            )
            out_5 = adaptive_avg_pool(x=x)

            np.testing.assert_allclose(
                out_1.numpy(), self.res_1_np, rtol=1e-5, atol=1e-8
            )
            np.testing.assert_allclose(
                out_2.numpy(), self.res_2_np, rtol=1e-5, atol=1e-8
            )
            np.testing.assert_allclose(
                out_3.numpy(), self.res_3_np, rtol=1e-5, atol=1e-8
            )
            np.testing.assert_allclose(
                out_4.numpy(), self.res_4_np, rtol=1e-5, atol=1e-8
            )
            np.testing.assert_allclose(
                out_5.numpy(), self.res_5_np, rtol=1e-5, atol=1e-8
            )


class TestOutputSizeTensor(UnittestBase):
    def init_info(self):
        self.shapes = [[1, 3, 6, 6]]
        self.save_path = os.path.join(self.temp_dir.name, self.path_prefix())

    def test_static(self):
        paddle.enable_static()
        main_prog = Program()
        startup_prog = Program()
        with program_guard(main_prog, startup_prog):
            fc = paddle.nn.Linear(6, 6)
            x = paddle.randn(self.shapes[0])
            x.stop_gradient = False
            feat = fc(x)  # [1,3,6,6]

            out1, out2 = self.call_func(feat)

            sgd = paddle.optimizer.SGD()
            sgd.minimize(paddle.mean(out1 + out2))
            self.assertTrue(self.var_prefix() in str(main_prog))

            exe = paddle.static.Executor()
            exe.run(startup_prog)
            res = exe.run(fetch_list=[out1, out2])
            np.testing.assert_allclose(res[0], res[1])
            paddle.static.save_inference_model(
                self.save_path, [x], [out1, out2], exe
            )
            # Test for Inference Predictor
            infer_outs = self.infer_prog()
            np.testing.assert_array_equal(infer_outs[0].shape, (1, 3, 3, 3))
            np.testing.assert_allclose(infer_outs[0], infer_outs[1])

    def path_prefix(self):
        return 'pool2d_tensor'

    def var_prefix(self):
        return "Vars["

    def call_func(self, x):
        # list[Tensor]
        output_size = [paddle.assign([3]), paddle.assign([3])]
        out1 = paddle.nn.functional.adaptive_avg_pool2d(x=x, output_size=[3, 3])
        out2 = paddle.nn.functional.adaptive_avg_pool2d(
            x=x, output_size=output_size
        )
        return out1, out2


class TestOutputSizeListTensor(TestOutputSizeTensor):
    def path_prefix(self):
        return 'pool2d_tensors'

    def call_func(self, x):
        # list[int, Tensor]
        output_size = [paddle.assign([3]), 3]
        out1 = paddle.nn.functional.adaptive_avg_pool2d(x=x, output_size=[3, 3])
        out2 = paddle.nn.functional.adaptive_avg_pool2d(
            x=x, output_size=output_size
        )
        return out1, out2


class TestOutputSizeListTensor2(TestOutputSizeTensor):
    def path_prefix(self):
        return 'pool2d_tensor2'

    def call_func(self, x):
        # A Tensor
        output_size = paddle.assign([3, 3])
        out1 = paddle.nn.functional.adaptive_avg_pool2d(x=x, output_size=[3, 3])
        out2 = paddle.nn.functional.adaptive_avg_pool2d(
            x=x, output_size=output_size
        )
        return out1, out2


if __name__ == '__main__':
    unittest.main()
