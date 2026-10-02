theory D
  imports
    B
begin

text \<open>A is redundant through B, and nothing here uses C.\<close>

definition d_const :: nat where "d_const = b_const"

end
