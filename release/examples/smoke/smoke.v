module smoke (input clk, input rst, input sel, input [7:0] a, input [7:0] b, output reg [7:0] y);
  reg [7:0] acc;
  wire [7:0] sum = acc + (sel ? a : b);
  always @(posedge clk) begin
    if (rst) acc <= 8'd0; else acc <= sum;
    y <= acc ^ a;
  end
endmodule
