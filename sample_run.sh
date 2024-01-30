isce2_topsapp --username <username> \
              --password <password> \
              --esa-username <esa-username> \
              --esa-password <esa-password> \
              --reference-scenes S1A_IW_SLC__1SDV_20220212T222803_20220212T222830_041886_04FCA3_2B3E \
                                 S1A_IW_SLC__1SDV_20220212T222828_20220212T222855_041886_04FCA3_A3E2  \
              --secondary-scenes S1A_IW_SLC__1SDV_20220131T222803_20220131T222830_041711_04F690_8F5F \
                                 S1A_IW_SLC__1SDV_20220131T222828_20220131T222855_041711_04F690_28D7  \
              --frame-id 25502 \
             > topsapp_img.out 2> topsapp_img.err
