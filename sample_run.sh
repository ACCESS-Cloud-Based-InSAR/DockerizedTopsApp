isce2_topsapp --username <username> \
              --password <password> \
              --esa-username <esa-username> \
              --esa-password <esa-password> \
              --reference-scenes S1B_IW_SLC__1SDV_20210723T014947_20210723T015014_027915_0354B4_B3A9 \
              --secondary-scenes S1B_IW_SLC__1SDV_20210711T014922_20210711T014949_027740_034F80_859D \
                                 S1B_IW_SLC__1SDV_20210711T014947_20210711T015013_027740_034F80_D404 \
                                 S1B_IW_SLC__1SDV_20210711T015011_20210711T015038_027740_034F80_376C \
             > topsapp_img.out 2> topsapp_img.err
